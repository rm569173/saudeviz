"""
Diagnostico da conexao Oracle da FIAP.

Roda uma bateria de verificacoes para descobrir o que a instancia permite,
antes de decidirmos o que vai para a camada Gold no Oracle e o que fica no
DuckDB local.

Como usar (no PowerShell, dentro da pasta do projeto):

    py testar_conexao.py

A senha e pedida num prompt oculto e NAO fica salva em lugar nenhum:
nem em arquivo, nem em variavel de ambiente persistente, nem no historico
do terminal.
"""
from __future__ import annotations

import getpass
import sys

import oracledb

from src import config

LARGURA = 68


def titulo(texto: str) -> None:
    print()
    print("=" * LARGURA)
    print(texto)
    print("=" * LARGURA)


def item(rotulo: str, valor: object, ok: bool | None = None) -> None:
    marca = "" if ok is None else ("[OK]   " if ok else "[FALHA] ")
    print(f"  {marca}{rotulo:<34} {valor}")


def testa(conexao: oracledb.Connection) -> None:
    """Executa as verificacoes que decidem a arquitetura da entrega."""

    # ---------------------------------------------------------------- 1
    titulo("1. IDENTIFICACAO DA INSTANCIA")
    with conexao.cursor() as cur:
        cur.execute("SELECT user, SYSDATE FROM dual")
        usuario, agora = cur.fetchone()
        item("Usuario conectado", usuario, True)
        item("Data/hora do servidor", agora)

        cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        try:
            item("Versao do Oracle", cur.fetchone()[0])
        except Exception:
            item("Versao do Oracle", "sem permissao de leitura em v$version")

    # ---------------------------------------------------------------- 2
    titulo("2. SELECT AI (DBMS_CLOUD_AI)")
    with conexao.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM all_objects WHERE object_name = 'DBMS_CLOUD_AI'")
        tem_select_ai = cur.fetchone()[0] > 0
    item("Pacote DBMS_CLOUD_AI disponivel", tem_select_ai, tem_select_ai)
    if not tem_select_ai:
        print("\n  Esperado: o Select AI so existe no Oracle Autonomous Database.")
        print("  A instancia da FIAP e um Oracle Database tradicional.")
        print("  -> O NL->SQL do MVP sera implementado por nos, e o script")
        print("     DBMS_CLOUD_AI fica entregue como evolucao documentada.")

    # ---------------------------------------------------------------- 3
    titulo("3. PERMISSOES DE DDL (criar as tabelas T_SAUDE_*)")
    with conexao.cursor() as cur:
        try:
            cur.execute("CREATE TABLE t_saude_teste_permissao (id NUMBER)")
            item("CREATE TABLE", "permitido", True)
            cur.execute("INSERT INTO t_saude_teste_permissao VALUES (1)")
            conexao.commit()
            item("INSERT", "permitido", True)
            cur.execute("DROP TABLE t_saude_teste_permissao")
            item("DROP TABLE", "permitido", True)
        except oracledb.DatabaseError as erro:
            item("CREATE TABLE", str(erro).strip().splitlines()[0], False)

    # ---------------------------------------------------------------- 4
    titulo("4. EXTERNAL TABLE (fonte 3 - CSV lido direto do banco)")
    with conexao.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM session_privs WHERE privilege = 'CREATE ANY DIRECTORY'")
        pode_diretorio = cur.fetchone()[0] > 0
        item("Privilegio CREATE ANY DIRECTORY", pode_diretorio, pode_diretorio)

        cur.execute("SELECT directory_name FROM all_directories ORDER BY 1")
        diretorios = [linha[0] for linha in cur.fetchall()]
        item("Diretorios visiveis", diretorios or "nenhum")

    if not pode_diretorio and not diretorios:
        print("\n  Sem DIRECTORY nao ha como criar EXTERNAL TABLE: o Oracle")
        print("  precisa de um caminho no servidor para ler o CSV, e o arquivo")
        print("  teria de estar na maquina do banco, nao na sua.")
        print("  -> Plano B: carregar o CSV como tabela comum e entregar o DDL")
        print("     da External Table documentado no script.")

    # ---------------------------------------------------------------- 5
    titulo("5. ESPACO DISPONIVEL (a camada Gold tem ~1 milhao de linhas)")
    with conexao.cursor() as cur:
        try:
            # max_bytes = -1 e o sentinela de cota ILIMITADA. O teste tem de
            # vir antes da divisao: -1/1024/1024 arredonda para zero e faria
            # uma cota ilimitada parecer cota esgotada.
            cur.execute("""
                SELECT tablespace_name,
                       max_bytes,
                       CASE WHEN max_bytes = -1
                            THEN NULL
                            ELSE ROUND(max_bytes / 1024 / 1024)
                       END                        AS cota_mb,
                       ROUND(bytes / 1024 / 1024) AS usado_mb
                  FROM user_ts_quotas
            """)
            cotas = cur.fetchall()
            if cotas:
                for tablespace, max_bytes, cota_mb, usado in cotas:
                    limite = "ILIMITADA" if max_bytes == -1 else f"{cota_mb} MB"
                    item(f"Tablespace {tablespace}",
                         f"cota {limite} | usado {usado} MB")
            else:
                item("Cota", "sem entrada em user_ts_quotas "
                             "(usa a cota padrao do tablespace)")

            cur.execute("""
                SELECT ROUND(SUM(bytes) / 1024 / 1024, 1)
                  FROM user_segments
            """)
            total = cur.fetchone()[0]
            item("Espaco ja ocupado pelo schema", f"{total or 0} MB")
        except oracledb.DatabaseError as erro:
            item("Cota", str(erro).strip().splitlines()[0], False)

    # ---------------------------------------------------------------- 6
    titulo("6. TABELAS JA EXISTENTES NO SEU SCHEMA")
    with conexao.cursor() as cur:
        cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tabelas = [linha[0] for linha in cur.fetchall()]
    if tabelas:
        item("Total", f"{len(tabelas)} tabelas")
        for tabela in tabelas[:25]:
            print(f"      - {tabela}")
        if len(tabelas) > 25:
            print(f"      ... e mais {len(tabelas) - 25}")
    else:
        item("Total", "schema vazio")


def main() -> int:
    titulo("DIAGNOSTICO DA CONEXAO ORACLE - SaudeViz")
    item("Host", config.ORACLE_HOST)
    item("Porta", config.ORACLE_PORTA)
    item("SID", config.ORACLE_SID)

    usuario = input("\n  Usuario Oracle [rm569173]: ").strip() or "rm569173"
    senha = getpass.getpass("  Senha (nao aparece na tela): ")

    if not senha:
        print("\n  Senha vazia. Abortado.")
        return 1

    try:
        conexao = oracledb.connect(user=usuario, password=senha,
                                   dsn=config.ORACLE_DSN)
    except oracledb.DatabaseError as erro:
        titulo("FALHA NA CONEXAO")
        print(f"  {erro}")
        print()
        print("  Causas mais comuns:")
        print("   ORA-01017  usuario ou senha invalidos")
        print("   ORA-12541  sem listener - rede bloqueando a porta 1521")
        print("   ORA-12514  SID errado (confira 'orcl' no SQL Developer)")
        print("   DPY-6005   sem rota ate o host - VPN da FIAP pode ser exigida")
        return 1

    try:
        testa(conexao)
    finally:
        conexao.close()

    titulo("DIAGNOSTICO CONCLUIDO")
    print("  Copie a saida acima e mande no chat para decidirmos a arquitetura.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
