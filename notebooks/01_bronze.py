# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Camada Bronze
# MAGIC
# MAGIC Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173
# MAGIC
# MAGIC Registra as três fontes como tabelas Delta, sem transformar nada. O que
# MAGIC entra é o que o DATASUS, a API do CNES e o IBGE publicaram.
# MAGIC
# MAGIC | Fonte | Formato | Origem |
# MAGIC |---|---|---|
# MAGIC | 1 — SIH/SUS | `.dbc` | FTP do DATASUS |
# MAGIC | 2 — CNES estabelecimentos | JSON | API REST do Ministério da Saúde |
# MAGIC | 2b — CNES leitos | `.dbc` | FTP do DATASUS |
# MAGIC | 3 — População municipal | CSV | API do IBGE |
# MAGIC
# MAGIC A decodificação do `.dbc` roda fora do Databricks: é um formato
# MAGIC proprietário do DATASUS que exige a extensão C `pyreaddbc` e acesso FTP,
# MAGIC pouco práticos em compute serverless. O ingestor está em
# MAGIC `src/ingestao/` e roda com `py -m src.ingestao.extrai_sih`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Parâmetros

# COMMAND ----------

CATALOGO = "workspace"
SCHEMA_LANDING = "saudeviz"
VOLUME_LANDING = "landing"
SCHEMA_BRONZE = "saudeviz_bronze"

LANDING = f"/Volumes/{CATALOGO}/{SCHEMA_LANDING}/{VOLUME_LANDING}"

# Recorte do MVP: região Sudeste completa.
UFS = ["ES", "MG", "RJ", "SP"]

# A ingestão vai até março/2025 de propósito: a competência do SIH é o mês de
# pagamento da AIH, não o da internação, e ~42% dos registros de um mês são de
# meses anteriores. Sem as competências de 2025 as internações de novembro e
# dezembro de 2024 ficariam faltando.
ANO_ANALISE = 2024

print(f"Landing zone : {LANDING}")
print(f"UFs          : {', '.join(UFS)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Criação do schema Bronze

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOGO}.{SCHEMA_BRONZE} "
          f"COMMENT 'SaudeViz - camada Bronze: dado bruto, sem transformacao'")
spark.sql(f"USE CATALOG {CATALOGO}")
spark.sql(f"USE SCHEMA {SCHEMA_BRONZE}")

display(spark.sql(f"SHOW SCHEMAS IN {CATALOGO} LIKE 'saudeviz*'"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Conferência da landing zone
# MAGIC
# MAGIC Antes de ler, confirmamos que o upload chegou completo. São esperados
# MAGIC 60 arquivos do SIH (4 UFs × 15 competências) mais os auxiliares.

# COMMAND ----------

import os

def lista_arquivos(caminho):
    """Percorre a landing zone recursivamente."""
    encontrados = []
    for entrada in dbutils.fs.ls(caminho):
        if entrada.isDir():
            encontrados.extend(lista_arquivos(entrada.path))
        else:
            encontrados.append((entrada.path, entrada.size))
    return encontrados

arquivos = lista_arquivos(LANDING)
total_mb = sum(tamanho for _, tamanho in arquivos) / 1e6

print(f"Arquivos na landing : {len(arquivos)}")
print(f"Volume total        : {total_mb:.1f} MB")

sih = [caminho for caminho, _ in arquivos if "/sih/" in caminho]
print(f"Arquivos do SIH     : {len(sih)}  (esperado: {len(UFS) * 15})")

if len(sih) != len(UFS) * 15:
    raise ValueError(
        f"Landing incompleta: {len(sih)} arquivos do SIH. "
        "Rode novamente 'py -m src.db.databricks_upload' na estacao local.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Fonte 1 — SIH/SUS
# MAGIC
# MAGIC Os parquets estão particionados por UF. A UF é derivada do caminho do
# MAGIC arquivo, e não de uma coluna interna do DBF.

# COMMAND ----------

from pyspark.sql import functions as F

bronze_sih = (
    spark.read
    .option("basePath", f"{LANDING}/sih")
    .parquet(f"{LANDING}/sih/*/*.parquet")
    .withColumn("_arquivo_origem", F.col("_metadata.file_path"))
    .withColumn("uf", F.regexp_extract(F.col("_metadata.file_path"),
                                       r"/sih/([A-Z]{2})/", 1))
    .withColumn("_ingerido_em", F.current_timestamp())
)

print(f"Colunas: {len(bronze_sih.columns)}")
print(f"Linhas : {bronze_sih.count():,}")
display(bronze_sih.groupBy("uf").count().orderBy("uf"))

# COMMAND ----------

(bronze_sih.write
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .partitionBy("uf")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_BRONZE}.sih_internacoes"))

spark.sql(f"""
    COMMENT ON TABLE {CATALOGO}.{SCHEMA_BRONZE}.sih_internacoes IS
    'Fonte 1 do challenge. Microdados de AIH do SIH/SUS, arquivos RD<UF><AA><MM>.dbc do FTP do DATASUS, convertidos para parquet sem alteracao de conteudo. ATENCAO: ANO_CMPT/MES_CMPT e a competencia de PAGAMENTO, nao a data da internacao.'
""")

display(spark.sql(f"DESCRIBE DETAIL {CATALOGO}.{SCHEMA_BRONZE}.sih_internacoes"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Fonte 2 — CNES: estabelecimentos e leitos
# MAGIC
# MAGIC O JSON da API tem atributos que variam entre estabelecimentos — é o dado
# MAGIC semiestruturado do desafio. O ingestor já o entrega achatado em parquet;
# MAGIC o JSON original fica em `dados/raw/cnes/estabelecimentos.jsonl`.

# COMMAND ----------

bronze_estabelecimentos = (
    spark.read.parquet(f"{LANDING}/cnes/estabelecimentos.parquet")
    .withColumn("_ingerido_em", F.current_timestamp())
)

(bronze_estabelecimentos.write
 .mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_BRONZE}.cnes_estabelecimentos"))

spark.sql(f"""
    COMMENT ON TABLE {CATALOGO}.{SCHEMA_BRONZE}.cnes_estabelecimentos IS
    'Fonte 2 do challenge. Cadastro de estabelecimentos do CNES obtido via API REST JSON do Ministerio da Saude, com enriquecimento dirigido pelos CNES que aparecem no SIH e nos leitos.'
""")

print(f"Estabelecimentos: {bronze_estabelecimentos.count():,}")

# COMMAND ----------

bronze_leitos = (
    spark.read.parquet(f"{LANDING}/cnes/leitos.parquet")
    .withColumn("_ingerido_em", F.current_timestamp())
)

(bronze_leitos.write
 .mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_BRONZE}.cnes_leitos"))

spark.sql(f"""
    COMMENT ON TABLE {CATALOGO}.{SCHEMA_BRONZE}.cnes_leitos IS
    'Leitos hospitalares por estabelecimento e tipo, arquivos LT<UF><AA><MM>.dbc do CNES. QT_SUS e o denominador do indicador de ocupacao.'
""")

print(f"Registros de leito: {bronze_leitos.count():,}")
display(bronze_leitos.groupBy("UF").agg(F.sum("QT_SUS").alias("leitos_sus")).orderBy("UF"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Fonte 3 — População municipal (CSV)
# MAGIC
# MAGIC Lê o CSV original, não o parquet: o desafio pede o formato CSV como
# MAGIC terceira fonte. No Oracle este arquivo seria uma `EXTERNAL TABLE`, cujo
# MAGIC DDL está em `src/db/ddl_oracle.sql`.

# COMMAND ----------

bronze_municipios = (
    spark.read
    .option("header", "true")
    .option("sep", ";")
    .option("inferSchema", "true")
    .option("encoding", "UTF-8")
    .csv(f"{LANDING}/ibge/populacao_municipios.csv")
    .withColumn("_ingerido_em", F.current_timestamp())
)

(bronze_municipios.write
 .mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_BRONZE}.ibge_municipios"))

spark.sql(f"""
    COMMENT ON TABLE {CATALOGO}.{SCHEMA_BRONZE}.ibge_municipios IS
    'Fonte 3 do challenge. Populacao municipal estimada pelo IBGE, lida do arquivo CSV. Traz regiao, porte e a meta de leitos pelo parametro OMS de 300 leitos por 100 mil habitantes.'
""")

print(f"Municipios: {bronze_municipios.count():,}")
display(bronze_municipios.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Resumo da camada Bronze

# COMMAND ----------

display(spark.sql(f"""
    SELECT table_name  AS tabela,
           comment     AS descricao
      FROM {CATALOGO}.information_schema.tables
     WHERE table_schema = '{SCHEMA_BRONZE}'
     ORDER BY table_name
"""))

# COMMAND ----------

for tabela in ["sih_internacoes", "cnes_estabelecimentos",
               "cnes_leitos", "ibge_municipios"]:
    n = spark.table(f"{CATALOGO}.{SCHEMA_BRONZE}.{tabela}").count()
    print(f"{tabela:26s} {n:>12,} linhas")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Próximo passo
# MAGIC
# MAGIC O notebook `02_prata` limpa, tipa, decodifica os domínios do SIH e troca
# MAGIC a dimensão temporal da competência de pagamento para a data de
# MAGIC internação.
