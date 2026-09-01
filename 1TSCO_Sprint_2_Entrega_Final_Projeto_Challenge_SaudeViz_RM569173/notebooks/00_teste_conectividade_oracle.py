# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Databricks alcança o Oracle da FIAP?
# MAGIC
# MAGIC Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173
# MAGIC
# MAGIC Responde a uma pergunta de arquitetura: o compute serverless do
# MAGIC Databricks consegue conectar em `oracle.fiap.com.br:1521`?
# MAGIC
# MAGIC | Resposta | O que muda |
# MAGIC |---|---|
# MAGIC | Sim | A camada Ouro vai do Spark direto para o Oracle |
# MAGIC | Não | A Ouro sai em parquet e a carga roda da estação local |
# MAGIC
# MAGIC Rode as células na ordem. Se a célula 1 falhar, as seguintes também
# MAGIC falham: é regra de rede, não configuração.
# MAGIC
# MAGIC Usamos `python-oracledb` em modo thin em vez do driver JDBC porque o
# MAGIC Free Edition roda só compute serverless, onde instalar bibliotecas Maven
# MAGIC é limitado. O modo thin é Python puro e instala com `%pip`.

# COMMAND ----------

# MAGIC %pip install oracledb --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. A porta 1521 está acessível?
# MAGIC
# MAGIC Teste de TCP puro, sem autenticação. Separa bloqueio de rede de erro de
# MAGIC credencial.

# COMMAND ----------

import socket
import time

HOST = "oracle.fiap.com.br"
PORTA = 1521
SID = "orcl"

inicio = time.time()
try:
    with socket.create_connection((HOST, PORTA), timeout=20):
        decorrido = time.time() - inicio
        print(f"[OK] Porta {PORTA} acessivel em {HOST} ({decorrido:.2f}s)")
        alcancavel = True
except Exception as erro:
    print(f"[FALHA] Nao foi possivel abrir {HOST}:{PORTA}")
    print(f"        {type(erro).__name__}: {erro}")
    print()
    print("  Leitura: o serverless do Databricks bloqueia saida para essa")
    print("  porta, ou a FIAP so aceita conexoes de faixas de IP conhecidas.")
    print("  -> Seguimos com a exportacao via parquet. Nao ha o que ajustar aqui.")
    alcancavel = False

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. A autenticação funciona?
# MAGIC
# MAGIC A senha vem do secret scope `saudeviz`, registrado com
# MAGIC `py -m src.db.databricks_secrets`. O Databricks mascara valores lidos de
# MAGIC secrets, então ela não aparece na saída.

# COMMAND ----------

if not alcancavel:
    print("Rede bloqueada na celula anterior. Pulando o teste de autenticacao.")
else:
    import oracledb

    usuario = dbutils.secrets.get("saudeviz", "oracle_user")
    senha = dbutils.secrets.get("saudeviz", "oracle_password")

    # A FIAP identifica a instancia por SID, nao por service name: o formato
    # curto "host:porta/nome" assumiria service name e falharia.
    dsn = (f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={HOST})"
           f"(PORT={PORTA}))(CONNECT_DATA=(SID={SID})))")

    try:
        conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
        with conexao.cursor() as cursor:
            cursor.execute("SELECT user, SYSDATE FROM dual")
            quem, quando = cursor.fetchone()
        print(f"[OK] Autenticado como {quem} | servidor em {quando}")
        conexao.close()
        autenticado = True
    except Exception as erro:
        print(f"[FALHA] {type(erro).__name__}: {erro}")
        autenticado = False

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Dá para gravar de verdade?
# MAGIC
# MAGIC Grava e apaga uma tabela de teste, medindo a taxa de inserção. É o que
# MAGIC define se vale carregar a camada Ouro daqui ou pela estação local.

# COMMAND ----------

if not alcancavel or not autenticado:
    print("Pre-requisitos nao atendidos. Pulando o teste de escrita.")
else:
    import time

    import oracledb

    LINHAS_TESTE = 5_000
    dados = [(i, f"registro {i}", i * 1.5) for i in range(LINHAS_TESTE)]

    conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                BEGIN
                    EXECUTE IMMEDIATE 'DROP TABLE t_saude_teste_databricks';
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
            """)
            cursor.execute("""
                CREATE TABLE t_saude_teste_databricks (
                    id     NUMBER,
                    texto  VARCHAR2(60),
                    valor  NUMBER(12, 2)
                )
            """)

            inicio = time.time()
            cursor.executemany(
                "INSERT INTO t_saude_teste_databricks VALUES (:1, :2, :3)", dados)
            conexao.commit()
            decorrido = time.time() - inicio

            cursor.execute("SELECT COUNT(*) FROM t_saude_teste_databricks")
            gravadas = cursor.fetchone()[0]

            print(f"[OK] {gravadas:,} linhas em {decorrido:.2f}s "
                  f"({gravadas / max(decorrido, 0.01):,.0f} linhas/s)")

            estimativa = 450_000 / max(gravadas / max(decorrido, 0.01), 1)
            print(f"     Estimativa para a camada Ouro (~450 mil linhas): "
                  f"{estimativa / 60:.1f} min")

            cursor.execute("DROP TABLE t_saude_teste_databricks")
            conexao.commit()
            print("     Tabela de teste removida.")
    finally:
        conexao.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Veredito

# COMMAND ----------

print("=" * 60)
print("RESULTADO DO TESTE DE CONECTIVIDADE")
print("=" * 60)
print(f"  Rede (porta 1521 aberta)  : {alcancavel}")
print(f"  Autenticacao Oracle       : {locals().get('autenticado', False)}")
print()
if alcancavel and locals().get("autenticado", False):
    print("  ARQUITETURA: Databricks grava a camada Ouro direto no Oracle.")
    print("  O painel Streamlit consulta o Oracle ao vivo, e o motor NL->SQL")
    print("  executa contra o banco - o mesmo papel do Select AI.")
else:
    print("  ARQUITETURA: a camada Ouro sai do Databricks como parquet,")
    print("  e a carga no Oracle roda da estacao local, que ja comprovou")
    print("  acesso ao banco. Nenhuma funcionalidade se perde - muda apenas")
    print("  onde o processo de carga e executado.")
print("=" * 60)
