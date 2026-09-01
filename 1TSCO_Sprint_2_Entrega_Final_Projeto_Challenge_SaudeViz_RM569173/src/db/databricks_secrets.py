"""
Registro da credencial do Oracle como secret do Databricks.

Senha em celula de notebook fica no historico de revisoes e em qualquer
copia do arquivo. O secret scope resolve: o notebook le por referencia e o
Databricks mascara a saida.

Este script le as credenciais das variaveis de ambiente e as envia. Nada e
escrito em disco nem aparece na tela.

Antes de rodar, defina no terminal:

    $env:DATABRICKS_HOST  = "https://dbc-ec79b4c9-62ce.cloud.databricks.com"
    $env:DATABRICKS_TOKEN = "<seu PAT>"
    $env:ORACLE_USER      = "rm569173"
    $env:ORACLE_PASSWORD  = "<sua senha do Oracle>"

Uso:
    py -m src.db.databricks_secrets
    py -m src.db.databricks_secrets --listar
    py -m src.db.databricks_secrets --remover
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

ESCOPO = "saudeviz"

CHAVES = {
    "oracle_user": "ORACLE_USER",
    "oracle_password": "ORACLE_PASSWORD",
    "oracle_dsn": "ORACLE_DSN",
}


def _cliente():
    from databricks.sdk import WorkspaceClient

    if not os.getenv("DATABRICKS_HOST") or not os.getenv("DATABRICKS_TOKEN"):
        raise SystemExit("Defina DATABRICKS_HOST e DATABRICKS_TOKEN no terminal.")
    return WorkspaceClient()


def registra() -> None:
    """Cria o scope e grava as credenciais do Oracle."""
    cliente = _cliente()

    valores = {
        "oracle_user": os.getenv("ORACLE_USER", ""),
        "oracle_password": os.getenv("ORACLE_PASSWORD", ""),
        "oracle_dsn": os.getenv("ORACLE_DSN", config.ORACLE_DSN),
    }

    faltando = [CHAVES[c] for c, v in valores.items() if not v]
    if faltando:
        raise SystemExit(
            "Variaveis de ambiente ausentes: " + ", ".join(faltando)
            + "\nDefina-as no terminal antes de rodar (veja o topo do arquivo).")

    escopos = {e.name for e in cliente.secrets.list_scopes()}
    if ESCOPO not in escopos:
        cliente.secrets.create_scope(scope=ESCOPO)
        log.info("Secret scope criado: %s", ESCOPO)
    else:
        log.info("Secret scope ja existia: %s", ESCOPO)

    for chave, valor in valores.items():
        cliente.secrets.put_secret(scope=ESCOPO, key=chave, string_value=valor)
        # Confirma o registro sem revelar o conteudo.
        log.info("Secret gravado: %s (%s caracteres)", chave, len(valor))

    print(f"\nPronto. Nos notebooks, leia assim:")
    print(f'    usuario = dbutils.secrets.get("{ESCOPO}", "oracle_user")')
    print(f'    senha   = dbutils.secrets.get("{ESCOPO}", "oracle_password")')
    print("\nO Databricks mascara automaticamente esses valores na saida das celulas.")


def lista() -> None:
    """Lista os scopes e as chaves registradas, sem mostrar valores."""
    cliente = _cliente()
    for escopo in cliente.secrets.list_scopes():
        print(f"scope: {escopo.name}")
        try:
            for segredo in cliente.secrets.list_secrets(scope=escopo.name):
                print(f"   - {segredo.key}")
        except Exception as erro:
            print(f"   (sem permissao de leitura: {erro})")


def remove() -> None:
    """Apaga o scope inteiro. Use ao terminar o projeto."""
    cliente = _cliente()
    cliente.secrets.delete_scope(scope=ESCOPO)
    log.info("Secret scope removido: %s", ESCOPO)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Secrets do Databricks")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--remover", action="store_true")
    args = parser.parse_args()

    if args.listar:
        lista()
    elif args.remover:
        remove()
    else:
        registra()
