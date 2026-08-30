# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Camada Ouro
# MAGIC
# MAGIC **Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173**
# MAGIC
# MAGIC Modelo dimensional e indicadores de negócio. É a camada que responde às
# MAGIC três perguntas do desafio sem varrer microdado:
# MAGIC
# MAGIC | Pergunta do desafio | Tabela que responde |
# MAGIC |---|---|
# MAGIC | Onde as internações estão crescendo? | `serie_temporal_uf`, `fato_internacao_mensal` |
# MAGIC | Quais perfis pressionam mais o sistema? | `fato_internacao_mensal` |
# MAGIC | Onde a capacidade está sendo ultrapassada? | `ind_capacidade_municipal` |
# MAGIC
# MAGIC Ao final, as tabelas são gravadas **direto no Oracle Database da FIAP** —
# MAGIC conectividade comprovada em `00_teste_conectividade_oracle` a
# MAGIC 6.401 linhas/s.

# COMMAND ----------

# MAGIC %pip install oracledb --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import Window

CATALOGO = "workspace"
SCHEMA_PRATA = "saudeviz_prata"
SCHEMA_OURO = "saudeviz_ouro"
VOLUME_SAIDA = f"/Volumes/{CATALOGO}/saudeviz/landing/ouro"

# Ano civil analisado, recortado por DATA DE INTERNAÇÃO. Os registros de 2023
# e 2025 presentes na Prata são as caudas das competências das pontas e são
# descartados aqui.
ANO_ANALISE = 2024

# Referência OMS de 300 leitos por 100 mil habitantes (piso da faixa 300-500).
LEITOS_POR_100MIL_OMS = 300

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOGO}.{SCHEMA_OURO} "
          f"COMMENT 'SaudeViz - camada Ouro: modelo dimensional e indicadores'")
spark.sql(f"USE CATALOG {CATALOGO}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Recorte temporal
# MAGIC
# MAGIC A Prata contém três anos porque a competência do SIH é o mês de
# MAGIC pagamento. Aqui ficamos apenas com as internações **ocorridas** em 2024.

# COMMAND ----------

internacoes_todas = spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.internacoes")

display(internacoes_todas.groupBy("ano").count().orderBy("ano"))

# COMMAND ----------

# Sem .cache(): o compute serverless nao aceita PERSIST TABLE
# (NOT_SUPPORTED_WITH_SERVERLESS). Nao faz falta - o serverless mantem cache
# de disco proprio, e a Prata ja esta particionada por uf e ano, entao o
# filtro abaixo e resolvido por particao, sem varrer a tabela inteira.
internacoes = internacoes_todas.filter(F.col("ano") == ANO_ANALISE)

total = internacoes.count()
print(f"Internacoes de {ANO_ANALISE}: {total:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Dimensões

# COMMAND ----------

dim_municipio = spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.municipios")

(dim_municipio.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.dim_municipio"))

print(f"dim_municipio: {dim_municipio.count():,}")

# COMMAND ----------

leitos = spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.leitos")
estabelecimentos = spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.estabelecimentos")

# A base da dimensão é a tabela de leitos: é ela que define quem tem
# capacidade instalada. O cadastro da API entra como enriquecimento.
dim_estabelecimento = (
    leitos
    .join(estabelecimentos.drop("uf", "cod_municipio_6"), on="cnes", how="left")
    .withColumn("nome_fantasia",
                F.coalesce(F.col("nome_fantasia"),
                           F.concat(F.lit("Estabelecimento "), F.col("cnes"))))
    .withColumn("esfera", F.coalesce(F.col("esfera"), F.lit("Nao informada")))
)

(dim_estabelecimento.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.dim_estabelecimento"))

print(f"dim_estabelecimento: {dim_estabelecimento.count():,}")
print(f"leitos SUS no Sudeste: "
      f"{dim_estabelecimento.agg(F.sum('leitos_sus')).first()[0]:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Fato — internações mensais
# MAGIC
# MAGIC Grão: município de atendimento × competência × perfil de atendimento ×
# MAGIC complexidade × caráter da internação.
# MAGIC
# MAGIC As médias são calculadas **depois** das somas, nunca agregando médias
# MAGIC parciais — média de médias daria peso igual a grupos de tamanhos
# MAGIC diferentes.

# COMMAND ----------

fato = (
    internacoes
    .withColumnRenamed("cod_municipio_mov", "cod_municipio_6")
    .groupBy("cod_municipio_6", "uf", "ano", "mes", "competencia",
             "perfil_atendimento", "complexidade", "carater_internacao")
    .agg(
        F.count("*").alias("internacoes"),
        F.sum("dias_permanencia").alias("dias_permanencia"),
        F.sum("diarias_uti").alias("diarias_uti"),
        F.sum("obito").alias("obitos"),
        F.sum("transferido").alias("transferencias"),
        F.sum("longa_permanencia").alias("longa_permanencia"),
        F.sum("tem_comorbidade").alias("comorbidades"),
        F.sum("valor_total").alias("valor_total"),
        F.sum("valor_uti").alias("valor_uti"),
        F.sum("idade_anos").alias("_idade_total"),
    )
    .withColumn("permanencia_media",
                F.round(F.col("dias_permanencia") / F.col("internacoes"), 2))
    .withColumn("valor_medio_aih",
                F.round(F.col("valor_total") / F.col("internacoes"), 2))
    .withColumn("idade_media",
                F.round(F.col("_idade_total") / F.col("internacoes"), 1))
    .withColumn("taxa_mortalidade",
                F.round(100 * F.col("obitos") / F.col("internacoes"), 2))
    .withColumn("taxa_transferencia",
                F.round(100 * F.col("transferencias") / F.col("internacoes"), 2))
    .drop("_idade_total")
)

(fato.write.mode("overwrite").option("overwriteSchema", "true")
 .partitionBy("uf")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.fato_internacao_mensal"))

print(f"fato_internacao_mensal: {fato.count():,} linhas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Indicador de pressão assistencial
# MAGIC
# MAGIC ```
# MAGIC taxa_ocupacao = dias de permanência consumidos / leitos-dia disponíveis
# MAGIC                 leitos-dia = leitos SUS × dias do mês
# MAGIC ```
# MAGIC
# MAGIC Usamos os **dias reais de cada mês** (28, 30, 31), e não uma média de
# MAGIC 30,4 — como a dimensão temporal agora é a data de internação, essa
# MAGIC precisão passou a ser possível, e fevereiro deixa de parecer mais
# MAGIC pressionado do que é.
# MAGIC
# MAGIC Acima de 1,0 a demanda superou a capacidade instalada declarada ao SUS.
# MAGIC **É um alerta para investigar, não uma prova de colapso**: pode indicar
# MAGIC também leito não atualizado no CNES.

# COMMAND ----------

leitos_por_municipio = (
    dim_estabelecimento
    .groupBy("cod_municipio_6")
    .agg(F.sum("leitos_existentes").alias("leitos_existentes"),
         F.sum("leitos_sus").alias("leitos_sus"))
)

capacidade = (
    fato
    .groupBy("cod_municipio_6", "uf", "ano", "mes", "competencia")
    .agg(F.sum("internacoes").alias("internacoes"),
         F.sum("dias_permanencia").alias("dias_permanencia"),
         F.sum("diarias_uti").alias("diarias_uti"),
         F.sum("obitos").alias("obitos"),
         F.sum("transferencias").alias("transferencias"),
         F.sum("valor_total").alias("valor_total"))
    .join(leitos_por_municipio, on="cod_municipio_6", how="left")
    .join(dim_municipio.select("cod_municipio_6", "municipio", "uf_nome",
                               "regiao", "populacao", "porte",
                               "meta_leitos_oms"),
          on="cod_municipio_6", how="left")
    .fillna({"leitos_sus": 0, "leitos_existentes": 0, "populacao": 0})
    .withColumn("municipio",
                F.coalesce(F.col("municipio"),
                           F.concat(F.lit("Municipio "), F.col("cod_municipio_6"))))

    # Dias reais do mês em questão.
    .withColumn("_primeiro_dia",
                F.to_date(F.concat_ws("-", F.col("ano"), F.col("mes"), F.lit(1))))
    .withColumn("dias_no_mes", F.dayofmonth(F.last_day("_primeiro_dia")))
    .withColumn("leitos_dia_disponiveis",
                F.col("leitos_sus") * F.col("dias_no_mes"))

    .withColumn("taxa_ocupacao",
                F.when(F.col("leitos_dia_disponiveis") > 0,
                       F.round(F.col("dias_permanencia")
                               / F.col("leitos_dia_disponiveis"), 3)))
    .withColumn("internacoes_por_10mil_hab",
                F.when(F.col("populacao") > 0,
                       F.round(10000 * F.col("internacoes") / F.col("populacao"), 3)))
    .withColumn("leitos_por_100mil_hab",
                F.when(F.col("populacao") > 0,
                       F.round(100000 * F.col("leitos_sus") / F.col("populacao"), 3)))
    .withColumn("deficit_leitos_oms",
                F.greatest(F.col("meta_leitos_oms") - F.col("leitos_sus"), F.lit(0)))
    .withColumn("permanencia_media",
                F.round(F.col("dias_permanencia") / F.col("internacoes"), 2))
    .withColumn("taxa_mortalidade",
                F.round(100 * F.col("obitos") / F.col("internacoes"), 2))
    .withColumn("taxa_transferencia",
                F.round(100 * F.col("transferencias") / F.col("internacoes"), 2))
    .withColumn("custo_medio_aih",
                F.round(F.col("valor_total") / F.col("internacoes"), 2))
    .withColumn(
        "situacao",
        F.when(F.col("taxa_ocupacao").isNull(), "Sem leito SUS cadastrado")
         .when(F.col("taxa_ocupacao") > 1.00, "Critica")
         .when(F.col("taxa_ocupacao") > 0.85, "Atencao")
         .when(F.col("taxa_ocupacao") > 0.70, "Adequada")
         .otherwise("Folga"))
    .drop("_primeiro_dia")
)

(capacidade.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.ind_capacidade_municipal"))

print(f"ind_capacidade_municipal: {capacidade.count():,} municipios-mes")
display(capacidade.groupBy("situacao").count().orderBy(F.desc("count")))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Ranking de hospitais

# COMMAND ----------

rank_hospitais = (
    internacoes
    .groupBy("cnes", "uf")
    .agg(F.count("*").alias("internacoes"),
         F.sum("dias_permanencia").alias("dias_permanencia"),
         F.sum("diarias_uti").alias("diarias_uti"),
         F.sum("obito").alias("obitos"),
         F.sum("transferido").alias("transferencias"),
         F.sum("valor_total").alias("valor_total"))
    .join(dim_estabelecimento.select("cnes", "nome_fantasia", "cod_municipio_6",
                                     "esfera", "leitos_existentes", "leitos_sus",
                                     "latitude", "longitude"),
          on="cnes", how="left")
    .withColumn("nome_fantasia",
                F.coalesce(F.col("nome_fantasia"),
                           F.concat(F.lit("CNES "), F.col("cnes"))))
    .fillna({"leitos_sus": 0, "leitos_existentes": 0})
    .withColumn("permanencia_media",
                F.round(F.col("dias_permanencia") / F.col("internacoes"), 2))
    .withColumn("taxa_mortalidade",
                F.round(100 * F.col("obitos") / F.col("internacoes"), 2))
    .withColumn("taxa_transferencia",
                F.round(100 * F.col("transferencias") / F.col("internacoes"), 2))
    .withColumn("custo_medio_aih",
                F.round(F.col("valor_total") / F.col("internacoes"), 2))
    .withColumn("giro_leito_ano",
                F.when(F.col("leitos_sus") > 0,
                       F.round(F.col("internacoes") / F.col("leitos_sus"), 1)))
    .withColumn("ranking_regional",
                F.row_number().over(Window.orderBy(F.desc("internacoes"))))
)

(rank_hospitais.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.rank_hospitais"))

print(f"rank_hospitais: {rank_hospitais.count():,}")
display(rank_hospitais.orderBy("ranking_regional").limit(10)
        .select("ranking_regional", "nome_fantasia", "uf", "internacoes",
                "permanencia_media", "taxa_transferencia", "leitos_sus"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Série temporal por UF
# MAGIC
# MAGIC Insumo do modelo de previsão. Agora que o eixo é a data de internação,
# MAGIC a sazonalidade que aparecer aqui é real — na versão por competência ela
# MAGIC ficava borrada pela cauda de faturamento.

# COMMAND ----------

serie_temporal_uf = (
    fato
    .groupBy("uf", "ano", "mes", "competencia")
    .agg(F.sum("internacoes").alias("internacoes"),
         F.sum("dias_permanencia").alias("dias_permanencia"),
         F.sum("valor_total").alias("valor_total"),
         F.sum("obitos").alias("obitos"),
         F.sum("transferencias").alias("transferencias"))
    .withColumn("data",
                F.to_date(F.concat_ws("-", F.col("ano"), F.col("mes"), F.lit(1))))
    .orderBy("uf", "data")
)

(serie_temporal_uf.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.serie_temporal_uf"))

# Índice de sazonalidade: mês dividido pela média do ano.
sazonalidade = (
    serie_temporal_uf.groupBy("mes").agg(F.sum("internacoes").alias("internacoes"))
)
media = sazonalidade.agg(F.avg("internacoes")).first()[0]
display(sazonalidade
        .withColumn("indice_sazonal", F.round(F.col("internacoes") / F.lit(media), 3))
        .orderBy("mes"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Exportação para parquet
# MAGIC
# MAGIC O painel precisa de um retrato local para funcionar mesmo se o banco da
# MAGIC faculdade estiver fora do ar durante uma apresentação. Não é
# MAGIC desconfiança do Oracle: é a diferença entre um pitch que trava ao vivo e
# MAGIC um que continua.

# COMMAND ----------

TABELAS_OURO = [
    "dim_municipio", "dim_estabelecimento", "fato_internacao_mensal",
    "ind_capacidade_municipal", "rank_hospitais", "serie_temporal_uf",
]

for tabela in TABELAS_OURO:
    df = spark.table(f"{CATALOGO}.{SCHEMA_OURO}.{tabela}")
    (df.coalesce(1).write.mode("overwrite")
     .parquet(f"{VOLUME_SAIDA}/{tabela}"))
    print(f"{tabela:28s} {df.count():>10,} linhas exportadas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Carga no Oracle Database
# MAGIC
# MAGIC O DDL é gerado a partir do schema do Spark, o que evita divergência
# MAGIC entre o modelo do lakehouse e o do banco. Os `COMMENT ON` são escritos
# MAGIC em linguagem de negócio de propósito: são esses metadados que o tradutor
# MAGIC de linguagem natural consome — o mesmo insumo que o Select AI usaria.

# COMMAND ----------

import oracledb
from pyspark.sql import types as T

USUARIO = dbutils.secrets.get("saudeviz", "oracle_user")
SENHA = dbutils.secrets.get("saudeviz", "oracle_password")
DSN = dbutils.secrets.get("saudeviz", "oracle_dsn")

PREFIXO = "T_SAUDE_"
LOTE = 10_000

COMENTARIOS = {
    "dim_municipio":
        "Municipios brasileiros com populacao estimada IBGE 2024, regiao, porte e meta de leitos pelo parametro OMS de 300 leitos por 100 mil habitantes. Fonte 3 do challenge (CSV).",
    "dim_estabelecimento":
        "Estabelecimentos de saude do CNES com leitos existentes e leitos disponibilizados ao SUS. Fonte 2 do challenge (JSON via API REST).",
    "fato_internacao_mensal":
        "Internacoes do SIH/SUS agregadas por municipio de atendimento, mes de internacao, perfil de atendimento (capitulo CID-10), complexidade e carater. Fonte 1 do challenge. A dimensao temporal usa a DATA DE INTERNACAO, nao a competencia de pagamento.",
    "ind_capacidade_municipal":
        "Pressao assistencial por municipio e mes. taxa_ocupacao = dias de permanencia consumidos dividido por leitos SUS vezes os dias do mes. Acima de 1 a demanda superou a capacidade instalada declarada ao SUS.",
    "rank_hospitais":
        "Ranking de estabelecimentos por volume de internacoes SUS, com permanencia media, mortalidade, taxa de transferencia, custo medio por AIH e giro de leito.",
    "serie_temporal_uf":
        "Serie mensal de internacoes por UF pela data de internacao, insumo do modelo de previsao de demanda.",
}


def tipo_oracle(campo: T.StructField) -> str:
    """Traduz o tipo do Spark para o tipo equivalente no Oracle."""
    tipo = campo.dataType
    if isinstance(tipo, (T.IntegerType, T.LongType, T.ShortType, T.ByteType)):
        return "NUMBER(18)"
    if isinstance(tipo, (T.DoubleType, T.FloatType, T.DecimalType)):
        return "NUMBER(20, 4)"
    if isinstance(tipo, T.DateType):
        return "DATE"
    if isinstance(tipo, T.TimestampType):
        return "TIMESTAMP"
    if isinstance(tipo, T.BooleanType):
        return "NUMBER(1)"
    return "VARCHAR2(300)"


def cria_tabela(cursor, nome_oracle: str, df, comentario: str) -> None:
    """Recria a tabela no Oracle a partir do schema do DataFrame."""
    colunas = ",\n    ".join(
        f"{campo.name} {tipo_oracle(campo)}" for campo in df.schema.fields)
    cursor.execute(f"""
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE {nome_oracle}';
        EXCEPTION WHEN OTHERS THEN NULL;
        END;
    """)
    cursor.execute(f"CREATE TABLE {nome_oracle} (\n    {colunas}\n)")
    cursor.execute(
        f"COMMENT ON TABLE {nome_oracle} IS '{comentario.replace(chr(39), chr(39) * 2)}'")


def carrega(cursor, conexao, nome_oracle: str, df) -> int:
    """Insere o DataFrame em lotes, com commit por lote."""
    pandas_df = df.toPandas()
    # O driver nao vincula tipos numpy nem valores nulos do pandas.
    pandas_df = pandas_df.astype(object).where(pandas_df.notna(), None)

    colunas = list(pandas_df.columns)
    marcadores = ", ".join(f":{i + 1}" for i in range(len(colunas)))
    insert = (f"INSERT INTO {nome_oracle} ({', '.join(colunas)}) "
              f"VALUES ({marcadores})")

    linhas = list(pandas_df.itertuples(index=False, name=None))
    for inicio in range(0, len(linhas), LOTE):
        cursor.executemany(insert, linhas[inicio:inicio + LOTE])
        conexao.commit()
    return len(linhas)

# COMMAND ----------

import time

conexao = oracledb.connect(user=USUARIO, password=SENHA, dsn=DSN)
inicio_total = time.time()

try:
    with conexao.cursor() as cursor:
        for tabela in TABELAS_OURO:
            df = spark.table(f"{CATALOGO}.{SCHEMA_OURO}.{tabela}")
            nome_oracle = f"{PREFIXO}{tabela.upper()}"

            inicio = time.time()
            cria_tabela(cursor, nome_oracle, df, COMENTARIOS[tabela])
            gravadas = carrega(cursor, conexao, nome_oracle, df)
            print(f"{nome_oracle:34s} {gravadas:>9,} linhas "
                  f"em {time.time() - inicio:6.1f}s")
finally:
    conexao.close()

print(f"\nCarga concluida em {time.time() - inicio_total:.1f}s")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Conferência no Oracle

# COMMAND ----------

conexao = oracledb.connect(user=USUARIO, password=SENHA, dsn=DSN)
try:
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT table_name
              FROM user_tables
             WHERE table_name LIKE 'T_SAUDE%'
             ORDER BY table_name
        """)
        tabelas_oracle = [linha[0] for linha in cursor.fetchall()]

        print(f"{'TABELA':34s} {'ORACLE':>12s} {'DATABRICKS':>12s}  OK")
        print("-" * 76)
        for nome_oracle in tabelas_oracle:
            cursor.execute(f"SELECT COUNT(*) FROM {nome_oracle}")
            n_oracle = cursor.fetchone()[0]
            tabela = nome_oracle.replace(PREFIXO, "").lower()
            n_spark = spark.table(f"{CATALOGO}.{SCHEMA_OURO}.{tabela}").count()
            marca = "sim" if n_oracle == n_spark else "NAO CONFERE"
            print(f"{nome_oracle:34s} {n_oracle:>12,} {n_spark:>12,}  {marca}")
finally:
    conexao.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Próximos passos
# MAGIC
# MAGIC 1. Baixar a Ouro para a estação local:
# MAGIC    `py -m src.db.databricks_upload --baixar-ouro`
# MAGIC 2. Modelo de previsão de demanda sobre `serie_temporal_uf`
# MAGIC 3. Motor NL→SQL sobre os `COMMENT ON` das tabelas `T_SAUDE_*`
# MAGIC 4. Painel Streamlit consultando o Oracle ao vivo
