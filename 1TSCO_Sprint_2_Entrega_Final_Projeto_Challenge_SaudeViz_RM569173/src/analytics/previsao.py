"""
Modelo preditivo de demanda hospitalar por UF.

Objetivo de negocio: estimar quantas internacoes cada UF tera nos proximos
meses para que a secretaria planeje leitos e orcamento antes da pressao
acontecer, em vez de reagir depois dela.

Tecnica: regressao linear com decomposicao aditiva de tendencia e
sazonalidade mensal (variaveis dummy de mes). E um modelo deliberadamente
simples e auditavel - o gestor consegue ler o coeficiente de cada mes -, o
que importa mais aqui do que ganhar alguns pontos de acuracia com um modelo
opaco.

Validacao: holdout temporal - treina nos primeiros meses da serie e mede o
erro nos ultimos, sem embaralhar as datas.

Uso: py -m src.analytics.previsao
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

MESES_TESTE = 3     # ultimos meses reservados para validacao
MESES_PREVISAO = 6  # horizonte projetado alem da serie observada


def _matriz_desenho(indice_tempo: np.ndarray, meses: np.ndarray) -> np.ndarray:
    """
    Monta a matriz de features: tendencia linear + dummies de mes.

    A dummy de janeiro e omitida (categoria de referencia) para evitar
    colinearidade perfeita com o intercepto.
    """
    dummies = np.zeros((len(meses), 11))
    for linha, mes in enumerate(meses):
        if mes > 1:
            dummies[linha, int(mes) - 2] = 1
    return np.column_stack([indice_tempo, dummies])


def treina_uf(serie: pd.DataFrame) -> tuple[LinearRegression, dict]:
    """Treina o modelo de uma UF e devolve o modelo e as metricas do holdout."""
    serie = serie.sort_values("data").reset_index(drop=True)
    serie["t"] = np.arange(len(serie))

    corte = len(serie) - MESES_TESTE
    treino, teste = serie.iloc[:corte], serie.iloc[corte:]

    x_treino = _matriz_desenho(treino["t"].values, treino["mes"].values)
    modelo = LinearRegression().fit(x_treino, treino["internacoes"].values)

    x_teste = _matriz_desenho(teste["t"].values, teste["mes"].values)
    previsto = modelo.predict(x_teste)

    metricas = {
        "mae": float(mean_absolute_error(teste["internacoes"], previsto)),
        "mape": float(mean_absolute_percentage_error(
            teste["internacoes"], previsto) * 100),
        "r2_treino": float(modelo.score(x_treino, treino["internacoes"].values)),
        "meses_treino": int(corte),
        "meses_teste": int(len(teste)),
    }

    # Retreina na serie completa para projetar o futuro.
    x_total = _matriz_desenho(serie["t"].values, serie["mes"].values)
    modelo_final = LinearRegression().fit(x_total, serie["internacoes"].values)
    return modelo_final, metricas


def projeta_uf(serie: pd.DataFrame, modelo: LinearRegression,
               metricas: dict) -> pd.DataFrame:
    """Gera historico ajustado + previsao futura com intervalo de confianca."""
    serie = serie.sort_values("data").reset_index(drop=True)
    serie["t"] = np.arange(len(serie))

    x_hist = _matriz_desenho(serie["t"].values, serie["mes"].values)
    ajuste = modelo.predict(x_hist)
    residuo_std = float(np.std(serie["internacoes"].values - ajuste))

    historico = pd.DataFrame({
        "uf": serie["uf"],
        "data": serie["data"],
        "competencia": serie["competencia"],
        "internacoes_reais": serie["internacoes"],
        "internacoes_previstas": np.round(ajuste).astype(int),
        "tipo": "historico",
    })

    ultima = serie["data"].max()
    datas_futuras = pd.date_range(
        ultima + pd.offsets.MonthBegin(1), periods=MESES_PREVISAO, freq="MS")
    t_futuro = np.arange(len(serie), len(serie) + MESES_PREVISAO)
    meses_futuro = datas_futuras.month.values

    futuro_previsto = modelo.predict(_matriz_desenho(t_futuro, meses_futuro))
    futuro = pd.DataFrame({
        "uf": serie["uf"].iloc[0],
        "data": datas_futuras,
        "competencia": datas_futuras.strftime("%Y%m"),
        "internacoes_reais": pd.NA,
        "internacoes_previstas": np.round(futuro_previsto).astype(int),
        "tipo": "previsao",
    })

    df = pd.concat([historico, futuro], ignore_index=True)
    # Intervalo de ~95% assumindo residuos aproximadamente normais.
    df["limite_inferior"] = (df["internacoes_previstas"] - 1.96 * residuo_std)
    df["limite_superior"] = (df["internacoes_previstas"] + 1.96 * residuo_std)
    df["limite_inferior"] = df["limite_inferior"].clip(lower=0).round().astype(int)
    df["limite_superior"] = df["limite_superior"].round().astype(int)
    df["erro_percentual"] = np.where(
        df["internacoes_reais"].notna(),
        ((df["internacoes_previstas"] - df["internacoes_reais"]).abs()
         / df["internacoes_reais"].replace(0, np.nan) * 100).round(2),
        np.nan)
    df["mape_validacao"] = round(metricas["mape"], 2)
    return df


def executa(min_meses: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Treina uma previsao por UF e materializa a saida na camada ouro."""
    serie_uf = pd.read_parquet(config.OURO / "serie_temporal_uf.parquet")

    previsoes, avaliacoes = [], []
    for uf, grupo in serie_uf.groupby("uf"):
        if len(grupo) < min_meses:
            log.warning("UF %s ignorada: apenas %s meses de serie", uf, len(grupo))
            continue
        modelo, metricas = treina_uf(grupo)
        previsoes.append(projeta_uf(grupo, modelo, metricas))
        avaliacoes.append({"uf": uf, **metricas})
        log.info("Previsao %s: MAPE %.2f%% | MAE %.0f internacoes",
                 uf, metricas["mape"], metricas["mae"])

    if not previsoes:
        raise RuntimeError(
            "Serie temporal curta demais para treinar. "
            "Amplie a janela em src/config.py (ANO_INICIO / MES_INICIO).")

    df_previsao = pd.concat(previsoes, ignore_index=True)
    df_avaliacao = pd.DataFrame(avaliacoes).round(3)

    df_previsao.to_parquet(config.OURO / "previsao_internacoes.parquet", index=False)
    (config.EVIDENCIAS / "modelos").mkdir(parents=True, exist_ok=True)
    df_avaliacao.to_csv(config.EVIDENCIAS / "modelos" / "avaliacao_previsao.csv",
                        index=False, sep=";", decimal=",", encoding="utf-8-sig")

    log.info("MAPE medio nacional: %.2f%%", df_avaliacao["mape"].mean())
    return df_previsao, df_avaliacao


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    previsao, avaliacao = executa()
    print(avaliacao.sort_values("mape").to_string(index=False))
    print(f"\nMAPE medio: {avaliacao['mape'].mean():.2f}%")
