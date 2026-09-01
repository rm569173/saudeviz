"""
Fonte 4 - Clima diario das capitais, via Open-Meteo.

Adiciona uma quarta fonte publica ao projeto para testar hipoteses que os
dados de saude sozinhos nao respondem:

  * chuva aumenta internacoes por acidente e causa externa?
  * frio aumenta internacoes por doenca respiratoria?
  * a estacao do ano tem efeito alem do ciclo semanal ja identificado?

Recorte nas quatro capitais porque clima e local: a media do estado inteiro
misturaria o litoral capixaba com a serra mineira. Sao 1,42 milhao de
internacoes em 2024, volume suficiente para o teste.

API: https://archive-api.open-meteo.com/v1/archive
Historico reanalisado, publico e sem chave de acesso.

Saida:
  dados/raw/clima/clima_capitais.csv
  dados/bronze/clima/clima_diario.parquet
"""
from __future__ import annotations

import json
import logging
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

API_CLIMA = "https://archive-api.open-meteo.com/v1/archive"

# Capitais do Sudeste, com o codigo IBGE de 6 digitos usado pelo SIH.
CAPITAIS = [
    {"cod_municipio_6": "320530", "municipio": "Vitoria", "uf": "ES",
     "latitude": -20.3155, "longitude": -40.3128},
    {"cod_municipio_6": "310620", "municipio": "Belo Horizonte", "uf": "MG",
     "latitude": -19.9167, "longitude": -43.9345},
    {"cod_municipio_6": "330455", "municipio": "Rio de Janeiro", "uf": "RJ",
     "latitude": -22.9068, "longitude": -43.1729},
    {"cod_municipio_6": "355030", "municipio": "Sao Paulo", "uf": "SP",
     "latitude": -23.5505, "longitude": -46.6333},
]

VARIAVEIS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_min",
    "precipitation_sum",
    "precipitation_hours",
    "windspeed_10m_max",
]

# Limiar de "dia com chuva". 1 mm separa chuva efetiva de garoa e de erro de
# arredondamento da reanalise.
CHUVA_MM = 1.0

# Estacoes do hemisferio sul, pelos solsticios e equinocios de 2024.
ESTACOES = [
    ("2024-01-01", "2024-03-19", "Verao"),
    ("2024-03-20", "2024-06-19", "Outono"),
    ("2024-06-20", "2024-09-21", "Inverno"),
    ("2024-09-22", "2024-12-20", "Primavera"),
    ("2024-12-21", "2024-12-31", "Verao"),
]

DESTINO_RAW = config.RAW / "clima"
DESTINO_BRONZE = config.BRONZE / "clima"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get_json(url: str, tentativas: int = 4) -> dict:
    """GET com retry exponencial."""
    ultima: Exception | None = None
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "SaudeViz/1.0 (FIAP Challenge)"})
            with urllib.request.urlopen(req, timeout=90, context=_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
            ultima = erro
            time.sleep(2 ** tentativa)
    raise RuntimeError(f"Open-Meteo indisponivel: {ultima}")


def estacao_do_ano(data: pd.Timestamp) -> str:
    """Estacao no hemisferio sul para uma data de 2024."""
    for inicio, fim, nome in ESTACOES:
        if pd.Timestamp(inicio) <= data <= pd.Timestamp(fim):
            return nome
    return "Indefinida"


def coleta_capital(capital: dict, ano: int = 2024) -> pd.DataFrame:
    """Baixa a serie diaria de uma capital."""
    params = urllib.parse.urlencode({
        "latitude": capital["latitude"],
        "longitude": capital["longitude"],
        "start_date": f"{ano}-01-01",
        "end_date": f"{ano}-12-31",
        "daily": ",".join(VARIAVEIS),
        "timezone": "America/Sao_Paulo",
    })
    dados = _get_json(f"{API_CLIMA}?{params}")

    df = pd.DataFrame(dados["daily"])
    df = df.rename(columns={
        "time": "data",
        "temperature_2m_max": "temp_max",
        "temperature_2m_min": "temp_min",
        "temperature_2m_mean": "temp_media",
        "apparent_temperature_min": "sensacao_min",
        "precipitation_sum": "chuva_mm",
        "precipitation_hours": "horas_chuva",
        "windspeed_10m_max": "vento_max",
    })
    df["data"] = pd.to_datetime(df["data"])
    for campo in ("cod_municipio_6", "municipio", "uf"):
        df[campo] = capital[campo]

    log.info("Clima %s/%s: %s dias", capital["municipio"], capital["uf"], len(df))
    return df


def ingere(ano: int = 2024, reprocessar: bool = False) -> pd.DataFrame:
    """Coleta o clima das quatro capitais e deriva os indicadores do estudo."""
    config.prepara_diretorios()
    DESTINO_RAW.mkdir(parents=True, exist_ok=True)
    DESTINO_BRONZE.mkdir(parents=True, exist_ok=True)

    alvo = DESTINO_BRONZE / "clima_diario.parquet"
    if alvo.exists() and not reprocessar:
        log.info("Clima ja coletado em %s", alvo)
        return pd.read_parquet(alvo)

    df = pd.concat([coleta_capital(c, ano) for c in CAPITAIS], ignore_index=True)

    # --- Indicadores derivados, que sao o que entra na analise --------------
    df["choveu"] = (df["chuva_mm"] >= CHUVA_MM).astype(int)
    df["estacao"] = df["data"].apply(estacao_do_ano)
    df["dia_semana"] = df["data"].dt.dayofweek
    df["mes"] = df["data"].dt.month

    # Faixas de temperatura por percentil DENTRO de cada capital: 18 graus e
    # frio em Vitoria e ameno em Sao Paulo, entao um limiar absoluto compararia
    # climas diferentes como se fossem o mesmo.
    df["faixa_temp"] = (
        df.groupby("cod_municipio_6")["temp_min"]
        .transform(lambda s: pd.qcut(s, 4, labels=["Muito frio", "Frio",
                                                   "Ameno", "Quente"]))
        .astype(str))

    df["chuva_faixa"] = pd.cut(
        df["chuva_mm"], bins=[-0.01, CHUVA_MM, 10, 30, 1000],
        labels=["Sem chuva", "Chuva fraca", "Chuva moderada", "Chuva forte"]
    ).astype(str)

    # Onda de frio: temperatura minima abaixo do percentil 10 da propria
    # capital, por pelo menos dois dias seguidos.
    df = df.sort_values(["cod_municipio_6", "data"])
    limite_frio = df.groupby("cod_municipio_6")["temp_min"].transform(
        lambda s: s.quantile(0.10))
    dia_frio = (df["temp_min"] <= limite_frio).astype(int)
    df["onda_frio"] = (
        (dia_frio == 1)
        & (dia_frio.groupby(df["cod_municipio_6"]).shift(1) == 1)
    ).astype(int)

    df.to_csv(DESTINO_RAW / "clima_capitais.csv", index=False,
              sep=";", encoding="utf-8")

    # O Spark recusa parquet com data em nanossegundos, que e o padrao do
    # pandas. Microssegundos os dois aceitam.
    df["data"] = df["data"].astype("datetime64[us]")
    df.to_parquet(alvo, index=False)

    log.info("Bronze clima: %s linhas x %s colunas", *df.shape)
    log.info("Dias com chuva: %s de %s (%.1f%%)",
             int(df["choveu"].sum()), len(df), 100 * df["choveu"].mean())
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    clima = ingere(reprocessar=True)
    print()
    print(clima.groupby(["municipio", "uf"]).agg(
        dias=("data", "count"),
        temp_min_media=("temp_min", "mean"),
        temp_min_absoluta=("temp_min", "min"),
        dias_com_chuva=("choveu", "sum"),
        chuva_total_mm=("chuva_mm", "sum"),
    ).round(1).to_string())
