"""
Camada OURO - modelo dimensional e indicadores de negocio.

Consolida as tres fontes num star schema enxuto, pensado para responder as
perguntas do desafio sem precisar varrer microdados:

  DIM_MUNICIPIO      municipio, UF, regiao, populacao, porte, meta OMS de leitos
  DIM_ESTABELECIMENTO estabelecimento CNES + leitos existentes e SUS
  FATO_INTERNACAO_MENSAL   internacoes por municipio x competencia x perfil
  IND_CAPACIDADE_MUNICIPAL indicador de pressao assistencial por municipio/mes
  RANK_HOSPITAIS           ranking de estabelecimentos por volume e permanencia

Saida: dados/ouro/*.parquet
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config
from src.medallion import prata

log = logging.getLogger(__name__)

# Dias do mes usados para converter leitos em leitos-dia disponiveis.
DIAS_POR_MES = 30.4


def dim_municipio() -> pd.DataFrame:
    """Dimensao de municipios a partir da fonte CSV/IBGE."""
    df = prata.limpa_municipios()
    dim = df[["cod_municipio_6", "cod_municipio", "municipio", "uf", "uf_nome",
              "regiao", "populacao", "porte", "meta_leitos_oms"]].copy()
    dim = dim.drop_duplicates(subset=["cod_municipio_6"])
    return dim


def dim_estabelecimento() -> pd.DataFrame:
    """Dimensao de estabelecimentos: JSON do CNES + leitos do CNES/LT."""
    est = prata.limpa_estabelecimentos()
    leitos = prata.limpa_leitos()

    dim = leitos.merge(
        est[["cnes", "nome_fantasia", "esfera", "tipo_gestao",
             "cod_tipo_unidade", "tem_atendimento_hospitalar",
             "tem_centro_cirurgico", "latitude", "longitude"]],
        on="cnes", how="left")
    dim["nome_fantasia"] = dim["nome_fantasia"].fillna("Estabelecimento " + dim["cnes"])
    dim["esfera"] = dim["esfera"].fillna("Nao informada")
    return dim


# Chaves do grao da tabela fato.
CHAVES_FATO = [
    "cod_municipio_6", "uf", "ano", "mes", "competencia",
    "perfil_atendimento", "complexidade", "carater_internacao",
]

# Somas parciais acumuladas por bloco. Medias NAO entram aqui: media de
# medias e um erro classico de agregacao distribuida - blocos com poucas
# internacoes pesariam tanto quanto blocos com muitas. As medias sao
# derivadas apenas no final, a partir das somas e das contagens.
SOMAS_FATO = [
    "internacoes", "dias_permanencia", "diarias_uti", "obitos",
    "transferencias", "longa_permanencia", "comorbidades",
    "valor_total", "valor_uti", "idade_total",
]


def _agrega_bloco_fato(df: pd.DataFrame) -> pd.DataFrame:
    """Reduz um bloco de internacoes ao grao da fato, so com somas."""
    bloco = df.rename(columns={"cod_municipio_mov": "cod_municipio_6"})
    bloco = bloco.assign(
        internacoes=1,
        idade_total=bloco["idade_anos"],
        transferencias=bloco["transferido"],
        comorbidades=bloco["tem_comorbidade"],
    )
    return (bloco.groupby(CHAVES_FATO, observed=True, as_index=False)
            .agg(internacoes=("internacoes", "sum"),
                 dias_permanencia=("dias_permanencia", "sum"),
                 diarias_uti=("diarias_uti", "sum"),
                 obitos=("obito", "sum"),
                 transferencias=("transferencias", "sum"),
                 longa_permanencia=("longa_permanencia", "sum"),
                 comorbidades=("comorbidades", "sum"),
                 valor_total=("valor_total", "sum"),
                 valor_uti=("valor_uti", "sum"),
                 idade_total=("idade_total", "sum")))


def fato_internacao_mensal() -> pd.DataFrame:
    """
    Fato agregado: uma linha por municipio de atendimento x competencia x
    perfil de atendimento x complexidade x carater.

    Percorre a prata particionada agregando bloco a bloco. Cada bloco cabe
    folgadamente na memoria; o que se acumula sao apenas as somas parciais,
    varias ordens de grandeza menores que os microdados.
    """
    parciais = []
    descartadas = 0
    for uf, competencia, bloco in prata.itera_internacoes():
        # Filtra pelo ano civil de internacao, nao pela competencia: os
        # arquivos de 2025 entram apenas para recuperar as internacoes de
        # 2024 faturadas com atraso, e os registros de 2023 que vieram nas
        # competencias do inicio de 2024 sao descartados.
        no_ano = bloco["ano"] == config.ANO_ANALISE
        descartadas += int((~no_ano).sum())
        bloco = bloco[no_ano]
        if bloco.empty:
            continue
        parciais.append(_agrega_bloco_fato(bloco))
        del bloco
    log.info("Agregados %s blocos da prata (%s registros fora de %s descartados)",
             len(parciais), f"{descartadas:,}", config.ANO_ANALISE)

    fato = (pd.concat(parciais, ignore_index=True)
            .groupby(CHAVES_FATO, observed=True, as_index=False)[SOMAS_FATO]
            .sum())

    # Metricas derivadas, calculadas so agora sobre os totais consolidados.
    fato["permanencia_media"] = (
        fato["dias_permanencia"] / fato["internacoes"]).round(2)
    fato["valor_medio_aih"] = (
        fato["valor_total"] / fato["internacoes"]).round(2)
    fato["idade_media"] = (fato["idade_total"] / fato["internacoes"]).round(1)
    fato["taxa_mortalidade"] = (
        fato["obitos"] / fato["internacoes"] * 100).round(2)
    fato["taxa_transferencia"] = (
        fato["transferencias"] / fato["internacoes"] * 100).round(2)
    fato = fato.drop(columns=["idade_total"])

    log.info("Fato mensal: %s linhas", len(fato))
    return fato


def ind_capacidade_municipal(fato: pd.DataFrame, municipios: pd.DataFrame,
                             estabelecimentos: pd.DataFrame) -> pd.DataFrame:
    """
    Indicador central do painel: pressao assistencial por municipio e mes.

    taxa_ocupacao = leitos-dia consumidos / leitos-dia disponiveis
      consumidos  = soma dos dias de permanencia das internacoes do mes
      disponiveis = leitos SUS do municipio x dias do mes

    Valores acima de 1,0 indicam que a demanda superou a capacidade instalada
    declarada ao SUS - exatamente a "regiao critica" que o desafio pede.
    """
    base = (fato.groupby(["cod_municipio_6", "uf", "ano", "mes", "competencia"],
                         as_index=False)
            .agg(internacoes=("internacoes", "sum"),
                 dias_permanencia=("dias_permanencia", "sum"),
                 diarias_uti=("diarias_uti", "sum"),
                 obitos=("obitos", "sum"),
                 valor_total=("valor_total", "sum")))

    leitos_mun = (estabelecimentos.groupby("cod_municipio_6", as_index=False)
                  [["leitos_existentes", "leitos_sus"]].sum())

    df = base.merge(leitos_mun, on="cod_municipio_6", how="left")
    df = df.merge(
        municipios[["cod_municipio_6", "municipio", "uf_nome", "regiao",
                    "populacao", "porte", "meta_leitos_oms"]],
        on="cod_municipio_6", how="left")

    df["leitos_sus"] = df["leitos_sus"].fillna(0)
    df["leitos_existentes"] = df["leitos_existentes"].fillna(0)
    df["municipio"] = df["municipio"].fillna("Municipio " + df["cod_municipio_6"])
    df["populacao"] = df["populacao"].fillna(0)

    df["leitos_dia_disponiveis"] = df["leitos_sus"] * DIAS_POR_MES
    df["taxa_ocupacao"] = np.where(
        df["leitos_dia_disponiveis"] > 0,
        df["dias_permanencia"] / df["leitos_dia_disponiveis"],
        np.nan)

    df["internacoes_por_10mil_hab"] = np.where(
        df["populacao"] > 0, df["internacoes"] / df["populacao"] * 10_000, np.nan)
    df["leitos_por_100mil_hab"] = np.where(
        df["populacao"] > 0, df["leitos_sus"] / df["populacao"] * 100_000, np.nan)
    df["deficit_leitos_oms"] = (df["meta_leitos_oms"] - df["leitos_sus"]).clip(lower=0)
    df["permanencia_media"] = (df["dias_permanencia"] / df["internacoes"]).round(2)
    df["taxa_mortalidade"] = (df["obitos"] / df["internacoes"] * 100).round(2)
    df["custo_medio_aih"] = (df["valor_total"] / df["internacoes"]).round(2)

    df["situacao"] = pd.cut(
        df["taxa_ocupacao"],
        bins=[-0.01, 0.70, 0.85, config.LIMITE_PRESSAO_ALERTA, np.inf],
        labels=["Folga", "Adequada", "Atencao", "Critica"],
    ).astype(str)
    df.loc[df["taxa_ocupacao"].isna(), "situacao"] = "Sem leito SUS cadastrado"

    for coluna in ("taxa_ocupacao", "internacoes_por_10mil_hab",
                   "leitos_por_100mil_hab"):
        df[coluna] = df[coluna].round(3)

    log.info("Indicador de capacidade: %s municipios-mes", len(df))
    return df


SOMAS_HOSPITAL = ["internacoes", "dias_permanencia", "diarias_uti",
                  "obitos", "transferencias", "valor_total"]


def rank_hospitais(estabelecimentos: pd.DataFrame) -> pd.DataFrame:
    """
    Ranking de estabelecimentos por volume, permanencia e custo.

    Assim como a fato, agrega em fluxo: soma parcial por bloco e consolidacao
    no final. A permanencia media so e dividida depois da soma total.
    """
    parciais = []
    colunas = ["cnes", "uf", "ano", "dias_permanencia", "diarias_uti",
               "obito", "transferido", "valor_total"]
    for uf, competencia, bloco in prata.itera_internacoes(colunas=colunas):
        bloco = bloco[bloco["ano"] == config.ANO_ANALISE]
        if bloco.empty:
            continue
        bloco = bloco.assign(internacoes=1,
                             transferencias=bloco["transferido"])
        parciais.append(
            bloco.groupby(["cnes", "uf"], observed=True, as_index=False)
            .agg(internacoes=("internacoes", "sum"),
                 dias_permanencia=("dias_permanencia", "sum"),
                 diarias_uti=("diarias_uti", "sum"),
                 obitos=("obito", "sum"),
                 transferencias=("transferencias", "sum"),
                 valor_total=("valor_total", "sum")))
        del bloco

    agg = (pd.concat(parciais, ignore_index=True)
           .groupby(["cnes", "uf"], observed=True, as_index=False)[SOMAS_HOSPITAL]
           .sum())
    agg["permanencia_media"] = (
        agg["dias_permanencia"] / agg["internacoes"]).round(2)

    df = agg.merge(
        estabelecimentos[["cnes", "nome_fantasia", "cod_municipio_6", "esfera",
                          "leitos_existentes", "leitos_sus", "latitude",
                          "longitude"]],
        on="cnes", how="left")
    df["nome_fantasia"] = df["nome_fantasia"].fillna("CNES " + df["cnes"])
    df["leitos_sus"] = df["leitos_sus"].fillna(0)
    df["taxa_mortalidade"] = (df["obitos"] / df["internacoes"] * 100).round(2)
    df["taxa_transferencia"] = (
        df["transferencias"] / df["internacoes"] * 100).round(2)
    df["custo_medio_aih"] = (df["valor_total"] / df["internacoes"]).round(2)
    df["giro_leito_ano"] = np.where(
        df["leitos_sus"] > 0, (df["internacoes"] / df["leitos_sus"]).round(1), np.nan)
    df["ranking_nacional"] = df["internacoes"].rank(
        ascending=False, method="min").astype(int)
    return df.sort_values("internacoes", ascending=False)


def serie_temporal_uf(fato: pd.DataFrame) -> pd.DataFrame:
    """Serie mensal por UF, insumo dos modelos de previsao."""
    serie = (fato.groupby(["uf", "ano", "mes", "competencia"], as_index=False)
             .agg(internacoes=("internacoes", "sum"),
                  dias_permanencia=("dias_permanencia", "sum"),
                  valor_total=("valor_total", "sum"),
                  obitos=("obitos", "sum")))
    serie["data"] = pd.to_datetime(
        serie["ano"].astype(str) + "-" + serie["mes"].astype(str).str.zfill(2) + "-01")
    return serie.sort_values(["uf", "data"])


def executa(reprocessar: bool = False) -> dict[str, int]:
    """Materializa toda a camada ouro em parquet."""
    config.OURO.mkdir(parents=True, exist_ok=True)

    municipios = dim_municipio()
    estabelecimentos = dim_estabelecimento()
    fato = fato_internacao_mensal()
    capacidade = ind_capacidade_municipal(fato, municipios, estabelecimentos)
    hospitais = rank_hospitais(estabelecimentos)
    serie = serie_temporal_uf(fato)

    tabelas = {
        "dim_municipio": municipios,
        "dim_estabelecimento": estabelecimentos,
        "fato_internacao_mensal": fato,
        "ind_capacidade_municipal": capacidade,
        "rank_hospitais": hospitais,
        "serie_temporal_uf": serie,
    }
    for nome, df in tabelas.items():
        df.to_parquet(config.OURO / f"{nome}.parquet", index=False)
        log.info("Ouro %s: %s linhas", nome, len(df))
    return {nome: len(df) for nome, df in tabelas.items()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    for tabela, linhas in executa().items():
        print(f"{tabela:28s} {linhas:>12,} linhas")
