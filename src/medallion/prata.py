"""
Camada PRATA - limpeza, tipagem e padronizacao.

Regras aplicadas:
  * tipos corretos (datas, numericos, categoricos);
  * decodificacao dos dominios do SIH (sexo, carater, complexidade, especialidade);
  * idade normalizada para anos (o SIH codifica dias/meses/anos em COD_IDADE);
  * remocao de registros invalidos (datas incoerentes, permanencia negativa);
  * deduplicacao por AIH.

Saida:
  dados/prata/internacoes.parquet
  dados/prata/estabelecimentos.parquet
  dados/prata/leitos.parquet
  dados/prata/municipios.parquet
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Dominios do SIH/SUS (dicionario oficial do DATASUS)
# --------------------------------------------------------------------------
SEXO = {"1": "Masculino", "2": "Feminino", "3": "Feminino"}

CARATER_INTERNACAO = {
    "01": "Eletivo",
    "02": "Urgencia",
    "03": "Acidente no trabalho",
    "04": "Acidente no trajeto",
    "05": "Outros acidentes de transito",
    "06": "Lesoes por agentes fisicos/quimicos",
}

COMPLEXIDADE = {"02": "Media complexidade", "03": "Alta complexidade"}

ESPECIALIDADE_LEITO = {
    "01": "Cirurgia",
    "02": "Obstetricia",
    "03": "Clinica medica",
    "04": "Cronicos",
    "05": "Psiquiatria",
    "06": "Pneumologia sanitaria",
    "07": "Pediatria",
    "08": "Reabilitacao",
    "09": "Hospital dia",
}

RACA_COR = {
    "01": "Branca",
    "02": "Preta",
    "03": "Parda",
    "04": "Amarela",
    "05": "Indigena",
    "99": "Sem informacao",
}

# Capitulos CID-10 resumidos, usados como "perfil de atendimento".
CAPITULOS_CID = [
    ("A00", "B99", "Doencas infecciosas e parasitarias"),
    ("C00", "D48", "Neoplasias"),
    ("D50", "D89", "Doencas do sangue e imunitarias"),
    ("E00", "E90", "Doencas endocrinas e metabolicas"),
    ("F00", "F99", "Transtornos mentais e comportamentais"),
    ("G00", "G99", "Doencas do sistema nervoso"),
    ("H00", "H59", "Doencas do olho e anexos"),
    ("H60", "H95", "Doencas do ouvido"),
    ("I00", "I99", "Doencas do aparelho circulatorio"),
    ("J00", "J99", "Doencas do aparelho respiratorio"),
    ("K00", "K93", "Doencas do aparelho digestivo"),
    ("L00", "L99", "Doencas da pele"),
    ("M00", "M99", "Doencas osteomusculares"),
    ("N00", "N99", "Doencas do aparelho geniturinario"),
    ("O00", "O99", "Gravidez, parto e puerperio"),
    ("P00", "P96", "Afeccoes do periodo perinatal"),
    ("Q00", "Q99", "Malformacoes congenitas"),
    ("R00", "R99", "Sintomas e achados anormais"),
    ("S00", "T98", "Lesoes e causas externas"),
    ("V01", "Y98", "Causas externas de morbimortalidade"),
    ("Z00", "Z99", "Fatores que influenciam o estado de saude"),
]


# Tipo de AIH. A distincao importa: as AIHs de longa permanencia sao poucas
# (0,4% em MG/dez-2024) mas tem permanencia media de 23,4 dias contra 4,8 das
# normais, e distorcem qualquer media que nao as separe.
TIPO_AIH = {"1": "Normal", "3": "Longa permanencia", "5": "Longa permanencia"}

FINANCIAMENTO = {
    "01": "Atencao basica",
    "02": "Media e alta complexidade",
    "04": "FAEC",
    "05": "Incentivo MAC",
    "06": "MAC - teto financeiro",
    "07": "Vigilancia em saude",
    "08": "Assistencia farmaceutica",
}

# Faixas do campo COBRANCA (motivo de saida/permanencia da AIH), conforme o
# dicionario do SIH/SUS. O agrupamento por faixa foi validado empiricamente:
# em MG/dez-2024 os codigos 41, 42 e 43 somaram exatamente 5.723 registros, o
# mesmo total de MORTE = 1, confirmando o bloco de obito.
FAIXAS_DESFECHO = [
    (11, 19, "Alta"),
    (21, 29, "Permanencia"),
    (31, 32, "Transferencia"),
    (41, 43, "Obito"),
    (51, 59, "Encerramento administrativo"),
    (61, 67, "Desfecho materno-neonatal"),
]


def desfecho_internacao(codigo: str) -> str:
    """Agrupa o motivo de saida da AIH na categoria de desfecho."""
    try:
        numero = int(codigo)
    except (TypeError, ValueError):
        return "Nao informado"
    for inicio, fim, nome in FAIXAS_DESFECHO:
        if inicio <= numero <= fim:
            return nome
    return "Nao classificado"


def capitulo_cid(codigo: str) -> str:
    """Mapeia um codigo CID-10 para o capitulo (perfil de atendimento)."""
    if not isinstance(codigo, str) or len(codigo) < 3:
        return "Nao informado"
    prefixo = codigo[:3].upper()
    for inicio, fim, nome in CAPITULOS_CID:
        if inicio <= prefixo <= fim:
            return nome
    return "Nao classificado"


def _idade_em_anos(idade: pd.Series, cod_idade: pd.Series) -> pd.Series:
    """COD_IDADE: 2=dias, 3=meses, 4=anos. Normaliza tudo para anos."""
    idade = pd.to_numeric(idade, errors="coerce")
    cod = cod_idade.astype(str).str.strip()
    anos = idade.where(cod == "4", 0.0)
    anos = anos.mask(cod == "3", idade / 12)
    anos = anos.mask(cod == "2", idade / 365)
    return anos.clip(lower=0, upper=120)


DESTINO_INTERNACOES = config.PRATA / "internacoes"


def arquivos_bronze_sih() -> list[Path]:
    """Lista os parquets da camada bronze do SIH, um por UF/competencia."""
    arquivos = sorted((config.BRONZE / "sih").rglob("*.parquet"))
    if not arquivos:
        raise FileNotFoundError(
            "Camada bronze do SIH vazia. Rode: py -m src.ingestao.extrai_sih")
    return arquivos


def caminho_prata(arquivo_bronze: Path) -> Path:
    """Espelha o particionamento do bronze na camada prata."""
    return DESTINO_INTERNACOES / arquivo_bronze.parent.name / arquivo_bronze.name


def limpa_internacoes(reprocessar: bool = False) -> pd.DataFrame:
    """
    Limpa o SIH/SUS arquivo a arquivo, gravando a prata particionada.

    O volume nao cabe na memoria: sao ~10,9 milhoes de internacoes a
    aproximadamente 1,35 KB por linha, o que daria cerca de 15 GB num unico
    DataFrame. Por isso cada UF/competencia e processada e gravada de forma
    independente, em dados/prata/internacoes/<UF>/<AAAAMM>.parquet.

    Devolve o resumo da execucao (uma linha por arquivo), e nao os dados:
    quem precisa das internacoes deve usar itera_internacoes().
    """
    config.prepara_diretorios()
    arquivos = arquivos_bronze_sih()
    log.info("Processando %s arquivos bronze do SIH", len(arquivos))

    resumo = []
    for posicao, arquivo in enumerate(arquivos, start=1):
        destino = caminho_prata(arquivo)
        if destino.exists() and not reprocessar:
            resumo.append({"uf": arquivo.parent.name, "competencia": arquivo.stem,
                           "linhas": -1, "status": "ja_existia"})
            continue
        bruto = pd.read_parquet(arquivo)
        bruto["UF"] = arquivo.parent.name
        limpo = _transforma_internacoes(bruto)
        destino.parent.mkdir(parents=True, exist_ok=True)
        limpo.to_parquet(destino, index=False)
        resumo.append({"uf": arquivo.parent.name, "competencia": arquivo.stem,
                       "linhas": len(limpo), "status": "ok"})
        if posicao % 24 == 0 or posicao == len(arquivos):
            log.info("  %s/%s arquivos limpos", posicao, len(arquivos))
        del bruto, limpo

    df_resumo = pd.DataFrame(resumo)
    validos = df_resumo[df_resumo["linhas"] >= 0]["linhas"].sum()
    log.info("Prata internacoes: %s arquivos, %s linhas gravadas",
             len(df_resumo), f"{validos:,}")
    return df_resumo


def itera_internacoes(colunas: list[str] | None = None):
    """
    Percorre a prata de internacoes um arquivo por vez.

    Devolve tuplas (uf, competencia, DataFrame). Quem consome agrega cada
    bloco e descarta, mantendo o uso de memoria proporcional ao maior
    arquivo e nao ao conjunto inteiro.
    """
    arquivos = sorted(DESTINO_INTERNACOES.rglob("*.parquet"))
    if not arquivos:
        raise FileNotFoundError(
            "Camada prata vazia. Rode: py -m src.medallion.prata")
    for arquivo in arquivos:
        yield arquivo.parent.name, arquivo.stem, pd.read_parquet(
            arquivo, columns=colunas)


def _transforma_internacoes(bruto: pd.DataFrame) -> pd.DataFrame:
    """Aplica limpeza, tipagem e decodificacao a um bloco do SIH/SUS."""
    df = pd.DataFrame(index=bruto.index)
    df["n_aih"] = bruto["N_AIH"].astype(str).str.strip()
    df["uf"] = bruto["UF"]

    # Competencia = mes em que a AIH foi processada e paga. NAO e o mes da
    # internacao: cerca de 42% dos registros de uma competencia sao de meses
    # anteriores. Mantida por rastreabilidade com o arquivo de origem, mas
    # nunca usada como dimensao temporal da analise.
    df["ano_processamento"] = pd.to_numeric(
        bruto["ANO_CMPT"], errors="coerce").astype("Int16")
    df["mes_processamento"] = pd.to_numeric(
        bruto["MES_CMPT"], errors="coerce").astype("Int8")
    df["competencia_processamento"] = (
        df["ano_processamento"].astype(str)
        + df["mes_processamento"].astype(str).str.zfill(2))

    df["cod_municipio_res"] = bruto["MUNIC_RES"].astype(str).str.strip()
    df["cod_municipio_mov"] = bruto["MUNIC_MOV"].astype(str).str.strip()
    df["cnes"] = bruto["CNES"].astype(str).str.strip().str.zfill(7)

    df["dt_internacao"] = pd.to_datetime(
        bruto["DT_INTER"], format="%Y%m%d", errors="coerce")
    df["dt_saida"] = pd.to_datetime(
        bruto["DT_SAIDA"], format="%Y%m%d", errors="coerce")
    # Dimensao temporal DA ANALISE: derivada da data real de internacao.
    # Toda agregacao mensal, sazonalidade, ocupacao e previsao usa estas
    # colunas - nunca a competencia de processamento.
    df["ano"] = df["dt_internacao"].dt.year.astype("Int16")
    df["mes"] = df["dt_internacao"].dt.month.astype("Int8")
    df["competencia"] = df["dt_internacao"].dt.strftime("%Y%m")

    # Defasagem entre internar e ser faturado, em meses. E a metrica que
    # justifica ingerir competencias ate M+3 e permite auditar a cobertura.
    df["defasagem_faturamento"] = (
        (df["ano_processamento"] - df["ano"]) * 12
        + (df["mes_processamento"] - df["mes"])).astype("Int16")

    df["dias_permanencia"] = pd.to_numeric(bruto["DIAS_PERM"], errors="coerce")
    df["qt_diarias"] = pd.to_numeric(bruto["QT_DIARIAS"], errors="coerce")
    df["diarias_uti"] = pd.to_numeric(
        bruto["UTI_MES_TO"], errors="coerce").fillna(0)
    df["obito"] = pd.to_numeric(
        bruto["MORTE"], errors="coerce").fillna(0).astype("Int8")

    df["idade_anos"] = _idade_em_anos(bruto["IDADE"], bruto["COD_IDADE"])
    df["faixa_etaria"] = pd.cut(
        df["idade_anos"],
        bins=[-0.01, 1, 4, 14, 19, 39, 59, 79, 120],
        labels=["< 1 ano", "1-4", "5-14", "15-19", "20-39", "40-59",
                "60-79", "80+"],
    ).astype(str)

    df["sexo"] = (bruto["SEXO"].astype(str).str.strip()
                  .map(SEXO).fillna("Nao informado"))
    df["raca_cor"] = (bruto["RACA_COR"].astype(str).str.strip().str.zfill(2)
                      .map(RACA_COR).fillna("Sem informacao"))
    df["carater_internacao"] = (
        bruto["CAR_INT"].astype(str).str.strip().str.zfill(2)
        .map(CARATER_INTERNACAO).fillna("Nao informado"))
    df["complexidade"] = (bruto["COMPLEX"].astype(str).str.strip().str.zfill(2)
                          .map(COMPLEXIDADE).fillna("Nao informado"))
    df["especialidade_leito"] = (
        bruto["ESPEC"].astype(str).str.strip().str.zfill(2)
        .map(ESPECIALIDADE_LEITO).fillna("Nao informado"))

    df["cid_principal"] = bruto["DIAG_PRINC"].astype(str).str.strip().str.upper()
    df["perfil_atendimento"] = df["cid_principal"].map(capitulo_cid)
    df["procedimento"] = bruto["PROC_REA"].astype(str).str.strip()

    df["valor_total"] = pd.to_numeric(
        bruto["VAL_TOT"], errors="coerce").fillna(0.0)
    df["valor_uti"] = pd.to_numeric(bruto["VAL_UTI"], errors="coerce").fillna(0.0)
    df["valor_serv_hospitalares"] = pd.to_numeric(
        bruto["VAL_SH"], errors="coerce").fillna(0.0)
    df["valor_serv_profissionais"] = pd.to_numeric(
        bruto["VAL_SP"], errors="coerce").fillna(0.0)
    df["financiamento"] = (bruto["FINANC"].astype(str).str.strip().str.zfill(2)
                           .map(FINANCIAMENTO).fillna("Nao informado"))

    df["cod_motivo_saida"] = bruto["COBRANCA"].astype(str).str.strip().str.zfill(2)
    df["desfecho"] = df["cod_motivo_saida"].map(desfecho_internacao)
    df["transferido"] = df["desfecho"].eq("Transferencia").astype("Int8")

    df["tipo_aih"] = (bruto["IDENT"].astype(str).str.strip()
                      .map(TIPO_AIH).fillna("Nao informado"))
    df["longa_permanencia"] = df["tipo_aih"].eq("Longa permanencia").astype("Int8")

    df["natureza_juridica"] = bruto["NAT_JUR"].astype(str).str.strip()
    df["cid_secundario"] = bruto["DIAGSEC1"].astype(str).str.strip().str.upper()
    df["tem_comorbidade"] = (
        df["cid_secundario"].str.len().ge(3)
        & ~df["cid_secundario"].isin(["0000", "000", "NAN"])).astype("Int8")
    df["proc_solicitado"] = bruto["PROC_SOLIC"].astype(str).str.strip()
    df["proc_alterado"] = df["proc_solicitado"].ne(df["procedimento"]).astype("Int8")

    antes = len(df)
    df = df.drop_duplicates(subset=["n_aih", "competencia"])
    df = df[df["dias_permanencia"].between(0, 365)]
    df = df[df["valor_total"] >= 0]
    df = df[df["dt_internacao"].notna()]
    if antes and (antes - len(df)) / antes > 0.05:
        log.warning("Descarte alto na limpeza: %s -> %s registros (%.2f%%)",
                    antes, len(df), 100 * (antes - len(df)) / antes)
    return df


def limpa_estabelecimentos(reprocessar: bool = False) -> pd.DataFrame:
    """Padroniza o JSON do CNES vindo da API."""
    alvo = config.PRATA / "estabelecimentos.parquet"
    if alvo.exists() and not reprocessar:
        return pd.read_parquet(alvo)

    bruto = pd.read_parquet(config.BRONZE / "cnes" / "estabelecimentos.parquet")

    df = pd.DataFrame(index=bruto.index)
    df["cnes"] = bruto["codigo_cnes"].astype(str).str.strip().str.zfill(7)
    df["nome_fantasia"] = (bruto["nome_fantasia"]
                           .fillna(bruto["nome_razao_social"])
                           .fillna("Nao informado").str.strip())
    df["cod_municipio"] = bruto["codigo_municipio"].astype(str).str.strip()
    df["cod_uf"] = bruto["codigo_uf"].astype(str).str.strip()
    df["uf"] = bruto["uf_consulta"]
    df["esfera"] = bruto["descricao_esfera_administrativa"].fillna("Nao informada")
    df["tipo_gestao"] = bruto["tipo_gestao"].fillna("N")
    df["cod_tipo_unidade"] = pd.to_numeric(
        bruto["codigo_tipo_unidade"], errors="coerce").astype("Int16")

    flags = [
        ("tem_atendimento_hospitalar",
         "estabelecimento_possui_atendimento_hospitalar"),
        ("tem_centro_cirurgico", "estabelecimento_possui_centro_cirurgico"),
        ("tem_centro_obstetrico", "estabelecimento_possui_centro_obstetrico"),
        ("tem_centro_neonatal", "estabelecimento_possui_centro_neonatal"),
    ]
    for nome, coluna in flags:
        df[nome] = pd.to_numeric(
            bruto[coluna], errors="coerce").fillna(0).astype("Int8")

    df["latitude"] = pd.to_numeric(
        bruto["latitude_estabelecimento_decimo_grau"], errors="coerce")
    df["longitude"] = pd.to_numeric(
        bruto["longitude_estabelecimento_decimo_grau"], errors="coerce")
    df["atende_sus"] = (
        bruto["estabelecimento_faz_atendimento_ambulatorial_sus"]
        .fillna("NAO").astype(str).str.upper().eq("SIM").astype("Int8"))

    df = df.drop_duplicates(subset=["cnes"])
    log.info("Prata estabelecimentos: %s registros", len(df))
    df.to_parquet(alvo, index=False)
    return df


def limpa_leitos(reprocessar: bool = False) -> pd.DataFrame:
    """Agrega os leitos do CNES por estabelecimento."""
    alvo = config.PRATA / "leitos.parquet"
    if alvo.exists() and not reprocessar:
        return pd.read_parquet(alvo)

    bruto = pd.read_parquet(config.BRONZE / "cnes" / "leitos.parquet")
    df = pd.DataFrame({
        "cnes": bruto["CNES"].astype(str).str.strip().str.zfill(7),
        "cod_municipio_6": bruto["CODUFMUN"].astype(str).str.strip(),
        "uf": bruto["UF"],
        "leitos_existentes": pd.to_numeric(
            bruto["QT_EXIST"], errors="coerce").fillna(0),
        "leitos_sus": pd.to_numeric(bruto["QT_SUS"], errors="coerce").fillna(0),
    })
    agregado = (df.groupby(["cnes", "cod_municipio_6", "uf"], as_index=False)
                [["leitos_existentes", "leitos_sus"]].sum())
    log.info("Prata leitos: %s estabelecimentos, %s leitos SUS",
             len(agregado), int(agregado["leitos_sus"].sum()))
    agregado.to_parquet(alvo, index=False)
    return agregado


def limpa_municipios(reprocessar: bool = False) -> pd.DataFrame:
    """A fonte IBGE ja chega padronizada; apenas promove para a camada prata."""
    alvo = config.PRATA / "municipios.parquet"
    if alvo.exists() and not reprocessar:
        return pd.read_parquet(alvo)
    df = pd.read_parquet(config.BRONZE / "ibge" / "municipios.parquet")
    df.to_parquet(alvo, index=False)
    return df


def executa(reprocessar: bool = False) -> dict[str, int]:
    """Roda a camada prata inteira e devolve a contagem por tabela."""
    config.prepara_diretorios()
    resumo = limpa_internacoes(reprocessar)
    gravadas = int(resumo.loc[resumo["linhas"] >= 0, "linhas"].sum())
    return {
        "internacoes": gravadas,
        "estabelecimentos": len(limpa_estabelecimentos(reprocessar)),
        "leitos": len(limpa_leitos(reprocessar)),
        "municipios": len(limpa_municipios(reprocessar)),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    for tabela, linhas in executa(reprocessar=True).items():
        print(f"{tabela:20s} {linhas:>12,} linhas")
