"""
Fonte 2 (semiestruturada) - CNES via API REST publica do Ministerio da Saude.

Endpoint: https://apidadosabertos.saude.gov.br/cnes/estabelecimentos
Retorna JSON com atributos variaveis por estabelecimento (nem todo
estabelecimento preenche os mesmos campos), o que caracteriza o dado
semiestruturado exigido pelo desafio.

ESTRATEGIA DE COLETA
--------------------
A colecao paginada tem duas limitacoes medidas na propria API:

  1. o parametro "limit" e travado em 20 registros, mesmo pedindo 1000;
  2. o CNES tem ~380 mil estabelecimentos no pais - so Sao Paulo exigiria
     cerca de 4.500 requisicoes, a maioria de clinicas, laboratorios e
     consultorios que nunca aparecem numa analise de internacao hospitalar.

Por isso a coleta e DIRIGIDA PELA DEMANDA ANALITICA: buscamos, um a um, os
estabelecimentos que efetivamente aparecem nas camadas ja materializadas -
os que possuem leito SUS cadastrado ou que registraram internacao no SIH.
Sao ~8 mil requisicoes com 100% de cobertura do que a solucao usa.

Consequencia de arquitetura: esta fonte deixa de ser independente e passa a
rodar DEPOIS do SIH e dos leitos, porque e deles que sai a lista de alvos.

Saida:
  dados/raw/cnes/estabelecimentos.jsonl   (JSON bruto preservado, 1 por linha)
  dados/bronze/cnes/estabelecimentos.parquet
"""
from __future__ import annotations

import json
import logging
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

DESTINO_RAW = config.RAW / "cnes"
DESTINO_BRONZE = config.BRONZE / "cnes"
CACHE_JSONL = DESTINO_RAW / "estabelecimentos.jsonl"

# Codigo IBGE da UF -> sigla. A API devolve apenas o codigo numerico.
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_TRAVA_ARQUIVO = threading.Lock()


def _get_json(url: str, tentativas: int = 4) -> dict | None:
    """
    GET com retry exponencial.

    Devolve None em 404: nem todo CNES registrado no SIH ainda consta na base
    de estabelecimentos da API (unidades desativadas, por exemplo).
    """
    ultima: Exception | None = None
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "SaudeViz/1.0 (FIAP Challenge)",
                              "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90, context=_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                return None
            ultima = erro
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
            ultima = erro
        espera = 2 ** tentativa
        log.debug("Falha na API CNES (%s). Nova tentativa em %ss.", ultima, espera)
        time.sleep(espera)
    log.warning("Desisti de %s apos %s tentativas: %s", url, tentativas, ultima)
    return None


def alvos_para_enriquecer() -> list[str]:
    """
    Lista os CNES que a solucao realmente usa.

    Uniao de dois conjuntos das camadas ja materializadas:
      * estabelecimentos com leito SUS cadastrado (denominador da ocupacao);
      * estabelecimentos que registraram internacao no SIH.
    """
    alvos: set[str] = set()

    leitos = config.PRATA / "leitos.parquet"
    if leitos.exists():
        df = pd.read_parquet(leitos)
        alvos |= set(df.loc[df["leitos_sus"] > 0, "cnes"].astype(str))

    # A prata de internacoes e particionada por UF/competencia: lemos apenas
    # a coluna cnes de cada bloco, o que mantem o custo de memoria trivial.
    for bloco in sorted((config.PRATA / "internacoes").rglob("*.parquet")):
        df = pd.read_parquet(bloco, columns=["cnes"])
        alvos |= set(df["cnes"].astype(str).unique())

    if not alvos:
        raise FileNotFoundError(
            "Nenhum alvo encontrado. Rode antes a ingestao do SIH e dos "
            "leitos e depois a camada prata (py -m src.medallion.prata).")

    return sorted(alvos)


def _le_cache() -> dict[str, dict]:
    """Le o cache JSONL de execucoes anteriores."""
    if not CACHE_JSONL.exists():
        return {}
    cache: dict[str, dict] = {}
    with CACHE_JSONL.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                continue  # linha truncada por interrupcao anterior
            cache[str(registro.get("codigo_cnes"))] = registro
    return cache


def _grava_cache(registro: dict) -> None:
    """Acrescenta um registro ao JSONL. Serializado entre as threads."""
    with _TRAVA_ARQUIVO:
        with CACHE_JSONL.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def busca_estabelecimento(cnes: str) -> dict | None:
    """Busca um estabelecimento pelo codigo CNES no endpoint individual."""
    codigo = str(cnes).lstrip("0") or "0"
    dados = _get_json(f"{config.API_CNES}/{urllib.parse.quote(codigo)}")
    if dados is None:
        return None
    dados["cnes_consultado"] = str(cnes)
    return dados


def coleta_paginada_uf(codigo_uf: int, max_paginas: int = 50) -> list[dict]:
    """
    Coleta paginada por UF - mantida como alternativa documentada.

    Atencao ao nome do parametro: a API aceita "codigo_uf" com o codigo
    numerico do IBGE. Passar "uf=SP" NAO filtra nada - o endpoint ignora o
    parametro desconhecido em silencio e devolve o pais inteiro.
    """
    coletados: list[dict] = []
    for pagina in range(max_paginas):
        params = urllib.parse.urlencode({
            "codigo_uf": codigo_uf,
            "limit": config.API_CNES_LIMITE_PAGINA,
            "offset": pagina * config.API_CNES_LIMITE_PAGINA,
        })
        dados = _get_json(f"{config.API_CNES}?{params}")
        lote = (dados or {}).get("estabelecimentos", [])
        if not lote:
            break
        coletados.extend(lote)
        time.sleep(config.API_CNES_PAUSA_SEG)
    return coletados


def ingere(alvos: list[str] | None = None, workers: int = 4,
           reprocessar: bool = False) -> pd.DataFrame:
    """Enriquece via API os estabelecimentos usados pela solucao."""
    config.prepara_diretorios()
    DESTINO_RAW.mkdir(parents=True, exist_ok=True)
    DESTINO_BRONZE.mkdir(parents=True, exist_ok=True)

    if reprocessar:
        CACHE_JSONL.unlink(missing_ok=True)

    alvos = alvos or alvos_para_enriquecer()
    cache = _le_cache()
    pendentes = [c for c in alvos if str(c).lstrip("0") not in cache
                 and str(c) not in cache]
    log.info("Alvos: %s | ja em cache: %s | a buscar: %s",
             len(alvos), len(alvos) - len(pendentes), len(pendentes))

    encontrados = 0
    ausentes = 0
    if pendentes:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futuros = {executor.submit(busca_estabelecimento, c): c
                       for c in pendentes}
            for concluidos, futuro in enumerate(as_completed(futuros), start=1):
                registro = futuro.result()
                if registro is None:
                    ausentes += 1
                else:
                    _grava_cache(registro)
                    encontrados += 1
                if concluidos % 250 == 0:
                    log.info("  %s/%s consultados (%s encontrados, %s ausentes)",
                             concluidos, len(pendentes), encontrados, ausentes)

    registros = list(_le_cache().values())
    if not registros:
        raise RuntimeError("A API nao devolveu nenhum estabelecimento.")

    # json_normalize achata o JSON aninhado em colunas tabulares.
    df = pd.json_normalize(registros)
    df["uf_consulta"] = (pd.to_numeric(df["codigo_uf"], errors="coerce")
                         .map(UF_POR_CODIGO).fillna("ND"))
    df.to_parquet(DESTINO_BRONZE / "estabelecimentos.parquet", index=False)

    log.info("Bronze CNES: %s linhas x %s colunas (%s nao encontrados na API)",
             df.shape[0], df.shape[1], ausentes)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    resultado = ingere()
    print(resultado.shape)
    print(resultado["uf_consulta"].value_counts().to_string())
