# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Clima e internação
# MAGIC
# MAGIC Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173
# MAGIC
# MAGIC Cruza uma quarta fonte pública — clima diário das capitais — com as
# MAGIC internações, para testar três hipóteses:
# MAGIC
# MAGIC | Hipótese | Como testar |
# MAGIC |---|---|
# MAGIC | Chuva aumenta acidentes | dias com e sem chuva × CID S00–T98 |
# MAGIC | Frio aumenta doença respiratória | temperatura mínima × CID J00–J99 |
# MAGIC | A estação do ano importa | estação × perfil de atendimento |
# MAGIC
# MAGIC Recorte nas quatro capitais: Vitória, Belo Horizonte, Rio de Janeiro e
# MAGIC São Paulo, com 1.421.225 internações em 2024. O clima é local, então
# MAGIC usar a média do estado misturaria o litoral capixaba com a serra mineira
# MAGIC e diluiria o sinal.
# MAGIC
# MAGIC Fonte do clima: Open-Meteo, reanálise histórica pública.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOGO = "workspace"
SCHEMA_PRATA = "saudeviz_prata"
SCHEMA_OURO = "saudeviz_ouro"
LANDING = f"/Volumes/{CATALOGO}/saudeviz/landing"
ANO_ANALISE = 2024

# Capitais do Sudeste, pelo código IBGE de 6 dígitos usado pelo SIH.
CAPITAIS = ["320530", "310620", "330455", "355030"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Clima diário

# COMMAND ----------

clima = spark.read.parquet(f"{LANDING}/clima/clima_diario.parquet")

(clima.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.saudeviz_bronze.clima_diario"))

print(f"Clima: {clima.count():,} dias-capital")
display(clima.groupBy("municipio", "uf").agg(
    F.count("*").alias("dias"),
    F.round(F.avg("temp_min"), 1).alias("temp_min_media"),
    F.min("temp_min").alias("temp_min_absoluta"),
    F.sum("choveu").alias("dias_com_chuva"),
    F.round(F.sum("chuva_mm"), 0).alias("chuva_total_mm")).orderBy("uf"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Internações diárias por capital e perfil
# MAGIC
# MAGIC Grão: capital × dia × capítulo CID-10. É o grão mais fino que permite
# MAGIC testar as hipóteses — clima é diário e local, e o efeito esperado atinge
# MAGIC perfis específicos, não o total.

# COMMAND ----------

internacoes = (
    spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.internacoes")
    .filter((F.col("ano") == ANO_ANALISE)
            & (F.col("cod_municipio_mov").isin(CAPITAIS)))
    .groupBy("cod_municipio_mov", "dt_internacao", "perfil_atendimento")
    .agg(F.count("*").alias("internacoes"),
         F.sum("dias_permanencia").alias("dias_permanencia"),
         F.sum(F.when(F.col("carater_internacao") == "Urgencia", 1)
               .otherwise(0)).alias("urgencias"))
    .withColumnRenamed("cod_municipio_mov", "cod_municipio_6")
    .withColumnRenamed("dt_internacao", "data")
)

print(f"Linhas: {internacoes.count():,}")
display(internacoes.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Junção
# MAGIC
# MAGIC `inner join` por capital e data. Todo dia de internação tem clima
# MAGIC correspondente, então nada se perde.

# COMMAND ----------

base = (
    internacoes
    .join(clima.select("cod_municipio_6", "data", "municipio", "uf",
                       "temp_min", "temp_max", "temp_media", "chuva_mm",
                       "choveu", "chuva_faixa", "faixa_temp", "estacao",
                       "onda_frio", "dia_semana"),
          on=["cod_municipio_6", "data"], how="inner")
)

base.write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.clima_internacao")

print(f"Base do estudo: {base.count():,} linhas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Hipótese 1 — chuva e acidentes
# MAGIC
# MAGIC Compara a média diária de internações por lesões e causas externas
# MAGIC (CID S00–T98) em dias com e sem chuva.
# MAGIC
# MAGIC A comparação controla o dia da semana: fim de semana tem menos
# MAGIC internação eletiva e mais acidente, e se os dias de chuva caíssem
# MAGIC desproporcionalmente em fins de semana, o efeito seria do calendário e
# MAGIC não da chuva.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT municipio,
# MAGIC        CASE WHEN choveu = 1 THEN 'Com chuva' ELSE 'Sem chuva' END AS condicao,
# MAGIC        COUNT(DISTINCT data)                       AS dias,
# MAGIC        ROUND(AVG(internacoes), 1)                 AS media_diaria,
# MAGIC        ROUND(AVG(urgencias), 1)                   AS urgencias_dia
# MAGIC   FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC  WHERE perfil_atendimento = 'Lesoes e causas externas'
# MAGIC    AND dia_semana <= 4
# MAGIC  GROUP BY municipio, choveu
# MAGIC  ORDER BY municipio, condicao;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Hipótese 1 refinada — intensidade da chuva
# MAGIC
# MAGIC Se a chuva causa acidente, o efeito deve crescer com a intensidade. Uma
# MAGIC diferença que aparece só no "com chuva versus sem chuva", sem gradiente,
# MAGIC é mais provavelmente ruído.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT chuva_faixa,
# MAGIC        COUNT(DISTINCT CONCAT(cod_municipio_6, data)) AS dias_capital,
# MAGIC        ROUND(AVG(internacoes), 1)                    AS acidentes_dia,
# MAGIC        ROUND(AVG(dias_permanencia) / AVG(internacoes), 2) AS permanencia_media
# MAGIC   FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC  WHERE perfil_atendimento = 'Lesoes e causas externas'
# MAGIC    AND dia_semana <= 4
# MAGIC  GROUP BY chuva_faixa
# MAGIC  ORDER BY CASE chuva_faixa
# MAGIC              WHEN 'Sem chuva' THEN 1 WHEN 'Chuva fraca' THEN 2
# MAGIC              WHEN 'Chuva moderada' THEN 3 ELSE 4 END;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Hipótese 2 — frio e doença respiratória
# MAGIC
# MAGIC A faixa de temperatura é calculada por quartil **dentro de cada
# MAGIC capital**: 18 graus é frio em Vitória e ameno em São Paulo, então um
# MAGIC limiar absoluto compararia climas diferentes como se fossem o mesmo.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT municipio,
# MAGIC        faixa_temp,
# MAGIC        COUNT(DISTINCT data)         AS dias,
# MAGIC        ROUND(AVG(temp_min), 1)      AS temp_min_media,
# MAGIC        ROUND(AVG(internacoes), 1)   AS respiratorias_dia
# MAGIC   FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC  WHERE perfil_atendimento = 'Doencas do aparelho respiratorio'
# MAGIC  GROUP BY municipio, faixa_temp
# MAGIC  ORDER BY municipio,
# MAGIC           CASE faixa_temp
# MAGIC              WHEN 'Muito frio' THEN 1 WHEN 'Frio' THEN 2
# MAGIC              WHEN 'Ameno' THEN 3 ELSE 4 END;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Correlação direta entre temperatura e internação respiratória

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT municipio,
# MAGIC        ROUND(CORR(temp_min, internacoes), 3)  AS corr_temp_min,
# MAGIC        ROUND(CORR(temp_max, internacoes), 3)  AS corr_temp_max,
# MAGIC        ROUND(CORR(chuva_mm, internacoes), 3)  AS corr_chuva
# MAGIC   FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC  WHERE perfil_atendimento = 'Doencas do aparelho respiratorio'
# MAGIC  GROUP BY municipio
# MAGIC  ORDER BY corr_temp_min;

# COMMAND ----------

# MAGIC %md
# MAGIC Correlação negativa significa que quanto **menor** a temperatura, **mais**
# MAGIC internações respiratórias.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Onda de frio
# MAGIC
# MAGIC Dois dias seguidos abaixo do percentil 10 da própria capital. O efeito do
# MAGIC frio sobre a via respiratória é cumulativo, e um único dia frio isolado
# MAGIC não deveria produzir o mesmo resultado.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT CASE WHEN onda_frio = 1 THEN 'Onda de frio' ELSE 'Demais dias' END AS condicao,
# MAGIC        COUNT(DISTINCT CONCAT(cod_municipio_6, data)) AS dias_capital,
# MAGIC        ROUND(AVG(temp_min), 1)                       AS temp_min_media,
# MAGIC        ROUND(AVG(internacoes), 1)                    AS respiratorias_dia
# MAGIC   FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC  WHERE perfil_atendimento = 'Doencas do aparelho respiratorio'
# MAGIC  GROUP BY onda_frio;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Hipótese 3 — estação do ano por perfil
# MAGIC
# MAGIC Índice acima de 1 significa que o perfil concentra mais internações
# MAGIC naquela estação do que a média do ano.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH por_estacao AS (
# MAGIC     SELECT perfil_atendimento,
# MAGIC            estacao,
# MAGIC            SUM(internacoes)              AS internacoes,
# MAGIC            COUNT(DISTINCT data)          AS dias
# MAGIC       FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC      GROUP BY perfil_atendimento, estacao
# MAGIC ), com_media AS (
# MAGIC     SELECT perfil_atendimento, estacao,
# MAGIC            internacoes / dias                                        AS por_dia,
# MAGIC            AVG(internacoes / dias) OVER (PARTITION BY perfil_atendimento) AS media_perfil,
# MAGIC            SUM(internacoes) OVER (PARTITION BY perfil_atendimento)    AS total_perfil
# MAGIC       FROM por_estacao
# MAGIC )
# MAGIC SELECT perfil_atendimento,
# MAGIC        estacao,
# MAGIC        ROUND(por_dia, 1)                     AS internacoes_dia,
# MAGIC        ROUND(por_dia / media_perfil, 3)      AS indice_sazonal
# MAGIC   FROM com_media
# MAGIC  WHERE total_perfil >= 20000
# MAGIC  ORDER BY perfil_atendimento,
# MAGIC           CASE estacao WHEN 'Verao' THEN 1 WHEN 'Outono' THEN 2
# MAGIC                        WHEN 'Inverno' THEN 3 ELSE 4 END;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Resumo — quais hipóteses se sustentaram

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH respiratoria AS (
# MAGIC     SELECT ROUND(AVG(CASE WHEN faixa_temp = 'Muito frio' THEN internacoes END), 1) AS frio,
# MAGIC            ROUND(AVG(CASE WHEN faixa_temp = 'Quente'     THEN internacoes END), 1) AS quente
# MAGIC       FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC      WHERE perfil_atendimento = 'Doencas do aparelho respiratorio'
# MAGIC ), acidente AS (
# MAGIC     SELECT ROUND(AVG(CASE WHEN choveu = 1 THEN internacoes END), 1) AS com_chuva,
# MAGIC            ROUND(AVG(CASE WHEN choveu = 0 THEN internacoes END), 1) AS sem_chuva
# MAGIC       FROM workspace.saudeviz_ouro.clima_internacao
# MAGIC      WHERE perfil_atendimento = 'Lesoes e causas externas'
# MAGIC        AND dia_semana <= 4
# MAGIC )
# MAGIC SELECT 'Frio aumenta internacao respiratoria' AS hipotese,
# MAGIC        r.frio      AS grupo_exposto,
# MAGIC        r.quente    AS grupo_controle,
# MAGIC        ROUND(100 * (r.frio - r.quente) / r.quente, 1) AS variacao_pct
# MAGIC   FROM respiratoria r
# MAGIC UNION ALL
# MAGIC SELECT 'Chuva aumenta acidente',
# MAGIC        a.com_chuva, a.sem_chuva,
# MAGIC        ROUND(100 * (a.com_chuva - a.sem_chuva) / a.sem_chuva, 1)
# MAGIC   FROM acidente a;

# COMMAND ----------

# MAGIC %md
# MAGIC ### Como ler o resumo
# MAGIC
# MAGIC `variacao_pct` é quanto o grupo exposto difere do controle. Positivo
# MAGIC confirma a hipótese; próximo de zero a refuta.
# MAGIC
# MAGIC Uma hipótese refutada é resultado, não fracasso: significa que a chuva ou
# MAGIC o frio não explicam a demanda hospitalar naquele perfil, e o planejamento
# MAGIC não deve contar com isso.
# MAGIC
# MAGIC E vale a ressalva de sempre: esta análise mostra **associação**, não
# MAGIC causa. Dias frios no Sudeste concentram-se no inverno, que também tem
# MAGIC circulação viral maior — o frio pode estar medindo a estação, e não o
# MAGIC efeito da temperatura em si.
