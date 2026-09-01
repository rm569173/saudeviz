"""
Analise exploratoria de dados (EDA) sobre a camada Ouro.

Gera as estatisticas e os graficos usados como evidencia da 4a entrega:
estatisticas descritivas, deteccao de outliers por IQR, matriz de correlacao
e sazonalidade mensal.

Uso: py -m src.analytics.eda
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

SAIDA = config.EVIDENCIAS / "eda"

# Metricas continuas analisadas no municipio-mes.
METRICAS = [
    "internacoes",
    "taxa_ocupacao",
    "permanencia_media",
    "custo_medio_aih",
    "taxa_mortalidade",
    "leitos_por_100mil_hab",
    "internacoes_por_10mil_hab",
]


def carrega_capacidade() -> pd.DataFrame:
    return pd.read_parquet(config.OURO / "ind_capacidade_municipal.parquet")


def carrega_fato() -> pd.DataFrame:
    return pd.read_parquet(config.OURO / "fato_internacao_mensal.parquet")


def estatisticas_descritivas(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo estatistico das metricas continuas, com assimetria e curtose."""
    presentes = [c for c in METRICAS if c in df.columns]
    desc = df[presentes].describe().T
    desc["assimetria"] = df[presentes].skew()
    desc["curtose"] = df[presentes].kurtosis()
    desc["nulos_pct"] = df[presentes].isna().mean() * 100
    return desc.round(3)


def detecta_outliers(df: pd.DataFrame, metrica: str = "taxa_ocupacao") -> pd.DataFrame:
    """
    Deteccao de outliers pelo criterio de Tukey (1,5 x intervalo interquartil).

    No contexto do painel, o outlier superior de taxa de ocupacao nao e ruido:
    e justamente o municipio em colapso que a gestao precisa enxergar.
    """
    serie = df[metrica].dropna()
    q1, q3 = serie.quantile([0.25, 0.75])
    iqr = q3 - q1
    limite_inf, limite_sup = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    marcados = df[(df[metrica] < limite_inf) | (df[metrica] > limite_sup)].copy()
    marcados["tipo_outlier"] = np.where(
        marcados[metrica] > limite_sup, "superior", "inferior")
    log.info("%s: Q1=%.3f Q3=%.3f IQR=%.3f -> %s outliers (%.2f%%)",
             metrica, q1, q3, iqr, len(marcados), 100 * len(marcados) / len(df))
    return marcados


def matriz_correlacao(df: pd.DataFrame) -> pd.DataFrame:
    """Correlacao de Pearson entre as metricas de pressao assistencial."""
    presentes = [c for c in METRICAS if c in df.columns]
    return df[presentes].corr(method="pearson").round(3)


def sazonalidade(fato: pd.DataFrame) -> pd.DataFrame:
    """Indice de sazonalidade mensal: mes / media anual."""
    por_mes = fato.groupby("mes", as_index=False)["internacoes"].sum()
    media = por_mes["internacoes"].mean()
    por_mes["indice_sazonal"] = (por_mes["internacoes"] / media).round(3)
    por_mes["variacao_vs_media_pct"] = (
        (por_mes["indice_sazonal"] - 1) * 100).round(1)
    return por_mes


def ranking_perfis(fato: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Perfis de atendimento que mais pressionam o sistema."""
    perfil = (fato.groupby("perfil_atendimento", as_index=False)
              .agg(internacoes=("internacoes", "sum"),
                   dias_permanencia=("dias_permanencia", "sum"),
                   valor_total=("valor_total", "sum"),
                   obitos=("obitos", "sum")))
    perfil["permanencia_media"] = (
        perfil["dias_permanencia"] / perfil["internacoes"]).round(2)
    perfil["custo_medio_aih"] = (
        perfil["valor_total"] / perfil["internacoes"]).round(2)
    perfil["participacao_internacoes_pct"] = (
        perfil["internacoes"] / perfil["internacoes"].sum() * 100).round(2)
    perfil["participacao_leitos_dia_pct"] = (
        perfil["dias_permanencia"] / perfil["dias_permanencia"].sum() * 100).round(2)
    # Pressao relativa: quanto o perfil ocupa de leito face ao que representa
    # em volume. Acima de 1 significa que consome mais leito do que o volume
    # sugere - o dado que a gestao precisa para priorizar.
    perfil["pressao_relativa"] = (
        perfil["participacao_leitos_dia_pct"]
        / perfil["participacao_internacoes_pct"]).round(2)
    return perfil.sort_values("dias_permanencia", ascending=False).head(top)


def executa() -> dict[str, pd.DataFrame]:
    """Roda a EDA completa e salva os CSVs de evidencia."""
    SAIDA.mkdir(parents=True, exist_ok=True)
    capacidade = carrega_capacidade()
    fato = carrega_fato()

    resultados = {
        "estatisticas_descritivas": estatisticas_descritivas(capacidade),
        "matriz_correlacao": matriz_correlacao(capacidade),
        "sazonalidade_mensal": sazonalidade(fato),
        "ranking_perfis": ranking_perfis(fato),
        "outliers_ocupacao": detecta_outliers(capacidade, "taxa_ocupacao"),
    }
    for nome, df in resultados.items():
        indice = nome in ("estatisticas_descritivas", "matriz_correlacao")
        df.to_csv(SAIDA / f"{nome}.csv", index=indice, sep=";",
                  decimal=",", encoding="utf-8-sig")
        log.info("EDA %s: %s linhas", nome, len(df))
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    saidas = executa()
    for nome, df in saidas.items():
        print(f"\n=== {nome} ===")
        print(df.head(12).to_string())
