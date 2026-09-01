"""
Carga da camada Ouro para o data warehouse (Oracle ou DuckDB).

Le os parquets de dados/ouro e grava nas tabelas T_SAUDE_*. O motor de destino
e escolhido automaticamente: Oracle quando ha credenciais configuradas,
DuckDB local caso contrario.

Uso:
    py -m src.db.carga              # motor automatico
    py -m src.db.carga --duckdb     # forca o DuckDB local
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config
from src.db.conexao import TABELAS, Motor, MotorDuckDB, obtem_motor

log = logging.getLogger(__name__)


def carrega(motor: Motor | None = None) -> pd.DataFrame:
    """Carrega todos os parquets da camada ouro presentes no disco."""
    motor = motor or obtem_motor()
    log.info("Motor de destino: %s", motor.nome)

    resultado = []
    for nome_logico, tabela in TABELAS.items():
        origem = config.OURO / f"{nome_logico}.parquet"
        if not origem.exists():
            log.info("Ignorando %s (parquet ainda nao gerado)", nome_logico)
            continue
        df = pd.read_parquet(origem)
        # O Oracle nao aceita colunas com nomes acima de 30 caracteres em
        # versoes antigas; a camada ouro ja respeita esse limite.
        linhas = motor.grava(df, tabela)
        log.info("%-28s -> %-32s %8s linhas", nome_logico, tabela, linhas)
        resultado.append({"tabela": tabela, "linhas": linhas})

    return pd.DataFrame(resultado)


def valida(motor: Motor | None = None) -> pd.DataFrame:
    """Contagem pos-carga, usada como evidencia de que a carga funcionou."""
    motor = motor or obtem_motor(somente_leitura=True)
    linhas = []
    for tabela in motor.tabelas_existentes():
        try:
            n = motor.consulta(f"SELECT COUNT(*) AS n FROM {tabela}").iloc[0, 0]
        except Exception as erro:
            n = f"erro: {erro}"
        linhas.append({"tabela": tabela, "registros": n})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Carga da camada Ouro")
    parser.add_argument("--duckdb", action="store_true",
                        help="forca o uso do DuckDB local")
    args = parser.parse_args()

    destino = MotorDuckDB() if args.duckdb else obtem_motor()
    carrega(destino)
    print()
    print(valida(destino).to_string(index=False))
