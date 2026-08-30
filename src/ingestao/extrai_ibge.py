"""
Fonte 3 (CSV / External Table) - Populacao municipal e malha territorial IBGE.

Gera um CSV com uma linha por municipio contendo populacao estimada, UF,
regiao e a classificacao de porte usada nas metas do painel. Esse CSV e
justamente o arquivo lido pelo Oracle como EXTERNAL TABLE.

Saida:
  dados/raw/populacao_municipios.csv
  dados/bronze/ibge/municipios.parquet
"""
from __future__ import annotations

import gzip
import json
import logging
import ssl
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

DESTINO = config.BRONZE / "ibge"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SaudeViz/1.0"})
    bruto = urllib.request.urlopen(req, timeout=120, context=_CTX).read()
    # A API do IBGE responde gzip mesmo sem Accept-Encoding negociado.
    return gzip.decompress(bruto) if bruto[:2] == b"\x1f\x8b" else bruto


def _extrai_uf(municipio: dict) -> dict | None:
    """
    Resolve a UF de um municipio na resposta do IBGE.

    A API expoe duas hierarquias e nem todo municipio preenche as duas:
    a antiga (microrregiao > mesorregiao > UF) e a atual
    (regiao-imediata > regiao-intermediaria > UF).
    """
    micro = municipio.get("microrregiao") or {}
    meso = micro.get("mesorregiao") or {}
    if meso.get("UF"):
        return meso["UF"]
    imediata = municipio.get("regiao-imediata") or {}
    intermediaria = imediata.get("regiao-intermediaria") or {}
    return intermediaria.get("UF")


def classifica_porte(pop: int) -> str:
    """Classificacao de porte municipal usada nas metas de capacidade."""
    if pop < 20_000:
        return "Pequeno I"
    if pop < 50_000:
        return "Pequeno II"
    if pop < 100_000:
        return "Medio"
    if pop < 500_000:
        return "Grande"
    return "Metropole"


def ingere(ano: int | None = None, reprocessar: bool = False) -> pd.DataFrame:
    """Monta a tabela de municipios com populacao, regiao e porte."""
    ano = ano or config.ANO_POPULACAO
    config.prepara_diretorios()  # o CSV vai para RAW, que pode nao existir
    DESTINO.mkdir(parents=True, exist_ok=True)
    alvo = DESTINO / "municipios.parquet"
    if alvo.exists() and not reprocessar:
        return pd.read_parquet(alvo)

    # Malha territorial: municipio -> UF -> regiao
    municipios = json.loads(_get(config.API_IBGE_MUNICIPIOS))
    linhas = []
    for m in municipios:
        uf = _extrai_uf(m)
        if uf is None:
            log.warning("Municipio sem UF resolvivel: %s", m.get("nome"))
            continue
        linhas.append({
            "cod_municipio": str(m["id"]),
            "municipio": m["nome"],
            "uf": uf["sigla"],
            "uf_nome": uf["nome"],
            "regiao": uf["regiao"]["nome"],
        })
    df_mun = pd.DataFrame(linhas)
    log.info("IBGE malha: %s municipios", len(df_mun))

    # Populacao estimada (agregado 6579, variavel 9324)
    pop_json = json.loads(_get(config.API_IBGE_POP.format(ano=ano)))
    series = pop_json[0]["resultados"][0]["series"]
    df_pop = pd.DataFrame([{
        "cod_municipio": s["localidade"]["id"],
        "populacao": pd.to_numeric(s["serie"].get(str(ano)), errors="coerce"),
    } for s in series])
    log.info("IBGE populacao %s: %s municipios", ano, len(df_pop))

    df = df_mun.merge(df_pop, on="cod_municipio", how="left")
    df["populacao"] = df["populacao"].fillna(0).astype(int)
    df["porte"] = df["populacao"].apply(classifica_porte)
    df["ano_referencia"] = ano
    # O SIH identifica municipio com 6 digitos (sem o digito verificador).
    df["cod_municipio_6"] = df["cod_municipio"].str[:6]
    # Meta de leitos derivada do parametro OMS (300 leitos / 100 mil hab).
    df["meta_leitos_oms"] = (
        df["populacao"] / 100_000 * config.LEITOS_POR_100MIL_OMS
    ).round(0).astype(int)

    df.to_csv(config.CSV_POPULACAO, index=False, encoding="utf-8", sep=";")
    df.to_parquet(alvo, index=False)
    log.info("CSV gerado para External Table: %s", config.CSV_POPULACAO)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    df = ingere()
    print(df.shape)
    print(df.head().to_string())
