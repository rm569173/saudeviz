"""
Segmentacao de municipios por perfil de pressao assistencial (K-Means).

Objetivo de negocio: separar os municipios que estao operando no limite
daqueles com folga, para que o investimento em leitos e a redistribuicao de
pacientes sejam direcionados por evidencia e nao por percepcao.

Tecnica: K-Means sobre variaveis padronizadas (StandardScaler), com o numero
de clusters escolhido pelo coeficiente de silhueta. Cada cluster recebe um
rotulo de negocio derivado dos seus centroides - explicabilidade e criterio
explicito de avaliacao do challenge.

Uso: py -m src.analytics.clusterizacao
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

VARIAVEIS = [
    "taxa_ocupacao_media",
    "permanencia_media",
    "leitos_por_100mil_hab",
    "internacoes_por_10mil_hab",
    "custo_medio_aih",
    "taxa_mortalidade",
]

# Municipios muito pequenos produzem indicadores instaveis (poucas AIHs no
# denominador), entao entram na analise apenas acima deste volume anual.
MIN_INTERNACOES_ANO = 100


def agrega_municipio() -> pd.DataFrame:
    """Consolida o indicador municipio-mes numa linha por municipio."""
    df = pd.read_parquet(config.OURO / "ind_capacidade_municipal.parquet")

    agregado = (df.groupby(
        ["cod_municipio_6", "municipio", "uf", "regiao", "porte"],
        as_index=False)
        .agg(populacao=("populacao", "max"),
             internacoes=("internacoes", "sum"),
             taxa_ocupacao_media=("taxa_ocupacao", "mean"),
             permanencia_media=("permanencia_media", "mean"),
             leitos_sus=("leitos_sus", "max"),
             leitos_por_100mil_hab=("leitos_por_100mil_hab", "mean"),
             internacoes_por_10mil_hab=("internacoes_por_10mil_hab", "mean"),
             custo_medio_aih=("custo_medio_aih", "mean"),
             taxa_mortalidade=("taxa_mortalidade", "mean")))

    antes = len(agregado)
    agregado = agregado[agregado["internacoes"] >= MIN_INTERNACOES_ANO]
    agregado = agregado.dropna(subset=VARIAVEIS)
    log.info("Municipios elegiveis: %s de %s", len(agregado), antes)
    return agregado


def escolhe_k(x: np.ndarray, candidatos=range(2, 8)) -> tuple[int, pd.DataFrame]:
    """Seleciona o numero de clusters pelo maior coeficiente de silhueta."""
    avaliacao = []
    for k in candidatos:
        modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
        rotulos = modelo.fit_predict(x)
        avaliacao.append({
            "k": k,
            "silhueta": round(float(silhouette_score(x, rotulos)), 4),
            "inercia": round(float(modelo.inertia_), 2),
        })
    df = pd.DataFrame(avaliacao)
    melhor = int(df.loc[df["silhueta"].idxmax(), "k"])
    log.info("k escolhido: %s (silhueta %.4f)", melhor, df["silhueta"].max())
    return melhor, df


def rotula_clusters(perfil: pd.DataFrame) -> dict[int, str]:
    """
    Traduz cada centroide num rotulo de negocio.

    A regra combina os dois eixos que interessam a gestao: quanto o municipio
    esta ocupado e quanta estrutura ele tem por habitante.
    """
    ocupacao_alta = perfil["taxa_ocupacao_media"].median()
    leitos_baixos = perfil["leitos_por_100mil_hab"].median()

    rotulos = {}
    for cluster, linha in perfil.iterrows():
        muito_ocupado = linha["taxa_ocupacao_media"] >= ocupacao_alta
        pouca_estrutura = linha["leitos_por_100mil_hab"] < leitos_baixos
        if muito_ocupado and pouca_estrutura:
            rotulo = "Critico - alta pressao, baixa estrutura"
        elif muito_ocupado:
            rotulo = "Pressionado - alta demanda com estrutura instalada"
        elif pouca_estrutura:
            rotulo = "Desassistido - baixa estrutura e baixa absorcao"
        else:
            rotulo = "Estavel - capacidade compativel com a demanda"
        rotulos[cluster] = rotulo
    return rotulos


def executa() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Roda a segmentacao completa e materializa a saida na camada ouro."""
    df = agrega_municipio()

    escalador = StandardScaler()
    x = escalador.fit_transform(df[VARIAVEIS])

    k, avaliacao_k = escolhe_k(x)
    modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
    df["cluster"] = modelo.fit_predict(x)

    # Centroides de volta na escala original, para leitura pelo gestor.
    perfil = pd.DataFrame(
        escalador.inverse_transform(modelo.cluster_centers_),
        columns=VARIAVEIS).round(3)
    perfil["municipios"] = df["cluster"].value_counts().sort_index().values
    perfil["populacao_total"] = (
        df.groupby("cluster")["populacao"].sum().sort_index().values)

    rotulos = rotula_clusters(perfil)
    perfil["perfil_cluster"] = perfil.index.map(rotulos)
    df["perfil_cluster"] = df["cluster"].map(rotulos)

    saida = df[["cod_municipio_6", "municipio", "uf", "regiao", "populacao",
                "internacoes", "taxa_ocupacao_media", "permanencia_media",
                "leitos_por_100mil_hab", "custo_medio_aih",
                "taxa_mortalidade", "cluster", "perfil_cluster"]].round(3)

    saida.to_parquet(config.OURO / "cluster_municipios.parquet", index=False)
    destino = config.EVIDENCIAS / "modelos"
    destino.mkdir(parents=True, exist_ok=True)
    perfil.to_csv(destino / "perfil_clusters.csv", sep=";", decimal=",",
                  encoding="utf-8-sig")
    avaliacao_k.to_csv(destino / "escolha_k_silhueta.csv", index=False, sep=";",
                       decimal=",", encoding="utf-8-sig")

    log.info("Clusterizacao concluida: %s municipios em %s grupos", len(saida), k)
    return saida, perfil, avaliacao_k


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    municipios, perfil, avaliacao = executa()
    print("\n=== Escolha de k ===")
    print(avaliacao.to_string(index=False))
    print("\n=== Perfil dos clusters ===")
    print(perfil.to_string())
