# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Camada Prata
# MAGIC
# MAGIC **Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173**
# MAGIC
# MAGIC Transforma o dado bruto em dado confiável. Cinco frentes:
# MAGIC
# MAGIC 1. **Tipagem** — datas, numéricos e categóricos com tipo correto
# MAGIC 2. **Decodificação** — os códigos do SIH viram texto de negócio
# MAGIC 3. **Dimensão temporal** — troca da competência de pagamento pela data real de internação
# MAGIC 4. **Enriquecimento** — capítulo CID-10, desfecho da internação, sinalizadores de qualidade
# MAGIC 5. **Qualidade** — deduplicação por AIH e descarte de registros inconsistentes
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## A correção mais importante deste notebook
# MAGIC
# MAGIC O campo `ANO_CMPT`/`MES_CMPT` do SIH é a **competência de pagamento** da
# MAGIC AIH, não o mês em que o paciente internou. Medimos isso nos próprios
# MAGIC dados: a competência `202401` traz **41,7% de internações de 2023**, e a
# MAGIC competência `202406` tem apenas **58%** de internações do próprio mês.
# MAGIC
# MAGIC | Defasagem entre internar e faturar | Participação |
# MAGIC |---|---|
# MAGIC | mesmo mês | 58% |
# MAGIC | 1 mês depois | 27% |
# MAGIC | 2 meses depois | 10% |
# MAGIC | 3 meses depois | 4% |
# MAGIC
# MAGIC Usar a competência como eixo de tempo faria o painel responder uma
# MAGIC pergunta **financeira** enquanto promete uma **assistencial**. Por isso
# MAGIC toda análise usa `dt_internacao`, e as competências de 2025 entram só
# MAGIC para recuperar as internações de dezembro/2024 faturadas com atraso.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Parâmetros

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import types as T

CATALOGO = "workspace"
SCHEMA_BRONZE = "saudeviz_bronze"
SCHEMA_PRATA = "saudeviz_prata"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOGO}.{SCHEMA_PRATA} "
          f"COMMENT 'SaudeViz - camada Prata: dado limpo, tipado e decodificado'")
spark.sql(f"USE CATALOG {CATALOGO}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Dicionários de domínio do SIH/SUS
# MAGIC
# MAGIC Os valores vêm do dicionário oficial do DATASUS. Traduzimos aqui, na
# MAGIC Prata, para que nenhuma consulta posterior precise saber que `02`
# MAGIC significa urgência — inclusive o tradutor de linguagem natural.

# COMMAND ----------

SEXO = {"1": "Masculino", "2": "Feminino", "3": "Feminino"}

CARATER_INTERNACAO = {
    "01": "Eletivo",
    "02": "Urgencia",
    "03": "Acidente no trabalho",
    "04": "Acidente no trajeto",
    "05": "Outros acidentes de transito",
    "06": "Lesoes por agentes fisicos/quimicos",
}

COMPLEXIDADE = {"02": "Media complexidade", "03": "Alta complexidade"}

ESPECIALIDADE_LEITO = {
    "01": "Cirurgia", "02": "Obstetricia", "03": "Clinica medica",
    "04": "Cronicos", "05": "Psiquiatria", "06": "Pneumologia sanitaria",
    "07": "Pediatria", "08": "Reabilitacao", "09": "Hospital dia",
}

RACA_COR = {
    "01": "Branca", "02": "Preta", "03": "Parda",
    "04": "Amarela", "05": "Indigena", "99": "Sem informacao",
}

# Tipo de AIH. A distinção importa: as de longa permanência são 0,4% dos
# registros mas têm permanência média de 23,4 dias contra 4,8 das normais.
# Sem separá-las, qualquer média de permanência sai inflada.
TIPO_AIH = {"1": "Normal", "3": "Longa permanencia", "5": "Longa permanencia"}

FINANCIAMENTO = {
    "01": "Atencao basica",
    "02": "Media e alta complexidade",
    "04": "FAEC",
    "05": "Incentivo MAC",
    "06": "MAC - teto financeiro",
    "07": "Vigilancia em saude",
    "08": "Assistencia farmaceutica",
}


def mapa_spark(dicionario: dict, padrao: str = "Nao informado"):
    """Converte um dicionário Python num MapType do Spark, com valor padrão."""
    pares = [F.lit(item) for chave, valor in dicionario.items()
             for item in (chave, valor)]
    mapa = F.create_map(*pares)

    def aplica(coluna):
        return F.coalesce(mapa[coluna], F.lit(padrao))

    return aplica

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Capítulos CID-10 e desfecho da internação
# MAGIC
# MAGIC Duas classificações por **faixa**, não por valor exato. Em vez de
# MAGIC encadear dezenas de `when`, montamos tabelas de referência e usamos
# MAGIC `broadcast join` — mais legível, e o Spark resolve em memória porque as
# MAGIC tabelas são minúsculas.

# COMMAND ----------

CAPITULOS_CID = [
    ("A00", "B99", "Doencas infecciosas e parasitarias"),
    ("C00", "D48", "Neoplasias"),
    ("D50", "D89", "Doencas do sangue e imunitarias"),
    ("E00", "E90", "Doencas endocrinas e metabolicas"),
    ("F00", "F99", "Transtornos mentais e comportamentais"),
    ("G00", "G99", "Doencas do sistema nervoso"),
    ("H00", "H59", "Doencas do olho e anexos"),
    ("H60", "H95", "Doencas do ouvido"),
    ("I00", "I99", "Doencas do aparelho circulatorio"),
    ("J00", "J99", "Doencas do aparelho respiratorio"),
    ("K00", "K93", "Doencas do aparelho digestivo"),
    ("L00", "L99", "Doencas da pele"),
    ("M00", "M99", "Doencas osteomusculares"),
    ("N00", "N99", "Doencas do aparelho geniturinario"),
    ("O00", "O99", "Gravidez, parto e puerperio"),
    ("P00", "P96", "Afeccoes do periodo perinatal"),
    ("Q00", "Q99", "Malformacoes congenitas"),
    ("R00", "R99", "Sintomas e achados anormais"),
    ("S00", "T98", "Lesoes e causas externas"),
    ("V01", "Y98", "Causas externas de morbimortalidade"),
    ("Z00", "Z99", "Fatores que influenciam o estado de saude"),
]

dim_cid = spark.createDataFrame(
    CAPITULOS_CID, schema=["cid_inicio", "cid_fim", "perfil_atendimento"])

# Faixas do campo COBRANCA (motivo de saída da AIH). O agrupamento foi
# validado empiricamente: em MG/dez-2024 os códigos 41, 42 e 43 somaram
# exatamente 5.723 registros, o mesmo total de MORTE = 1.
FAIXAS_DESFECHO = [
    (11, 19, "Alta"),
    (21, 29, "Permanencia"),
    (31, 32, "Transferencia"),
    (41, 43, "Obito"),
    (51, 59, "Encerramento administrativo"),
    (61, 67, "Desfecho materno-neonatal"),
]

dim_desfecho = spark.createDataFrame(
    FAIXAS_DESFECHO, schema=["cod_inicio", "cod_fim", "desfecho"])

display(dim_cid)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Internações — tipagem e decodificação

# COMMAND ----------

bruto = spark.table(f"{CATALOGO}.{SCHEMA_BRONZE}.sih_internacoes")

def cod(coluna, tamanho=2):
    """Normaliza um código do SIH: sem espaços, com zeros à esquerda."""
    return F.lpad(F.trim(F.col(coluna)), tamanho, "0")

prata = (
    bruto
    .select(
        F.trim(F.col("N_AIH")).alias("n_aih"),
        F.col("uf"),

        # Competência = mês de PAGAMENTO. Mantida só por rastreabilidade com o
        # arquivo de origem; nunca usada como dimensão temporal da análise.
        F.col("ANO_CMPT").cast("int").alias("ano_processamento"),
        F.col("MES_CMPT").cast("int").alias("mes_processamento"),

        F.trim(F.col("MUNIC_RES")).alias("cod_municipio_res"),
        F.trim(F.col("MUNIC_MOV")).alias("cod_municipio_mov"),
        F.lpad(F.trim(F.col("CNES")), 7, "0").alias("cnes"),

        F.to_date(F.col("DT_INTER"), "yyyyMMdd").alias("dt_internacao"),
        F.to_date(F.col("DT_SAIDA"), "yyyyMMdd").alias("dt_saida"),
        F.col("DIAS_PERM").cast("int").alias("dias_permanencia"),
        F.col("QT_DIARIAS").cast("int").alias("qt_diarias"),
        F.coalesce(F.col("UTI_MES_TO").cast("int"), F.lit(0)).alias("diarias_uti"),
        F.coalesce(F.col("MORTE").cast("int"), F.lit(0)).alias("obito"),

        F.col("IDADE").cast("double").alias("_idade"),
        F.trim(F.col("COD_IDADE")).alias("_cod_idade"),

        mapa_spark(SEXO)(F.trim(F.col("SEXO"))).alias("sexo"),
        mapa_spark(RACA_COR, "Sem informacao")(cod("RACA_COR")).alias("raca_cor"),
        mapa_spark(CARATER_INTERNACAO)(cod("CAR_INT")).alias("carater_internacao"),
        mapa_spark(COMPLEXIDADE)(cod("COMPLEX")).alias("complexidade"),
        mapa_spark(ESPECIALIDADE_LEITO)(cod("ESPEC")).alias("especialidade_leito"),
        mapa_spark(TIPO_AIH)(F.trim(F.col("IDENT"))).alias("tipo_aih"),
        mapa_spark(FINANCIAMENTO)(cod("FINANC")).alias("financiamento"),

        F.upper(F.trim(F.col("DIAG_PRINC"))).alias("cid_principal"),
        F.upper(F.trim(F.col("DIAGSEC1"))).alias("cid_secundario"),
        F.trim(F.col("PROC_REA")).alias("procedimento"),
        F.trim(F.col("PROC_SOLIC")).alias("proc_solicitado"),
        F.trim(F.col("NAT_JUR")).alias("natureza_juridica"),
        cod("COBRANCA").alias("cod_motivo_saida"),

        F.coalesce(F.col("VAL_TOT").cast("double"), F.lit(0.0)).alias("valor_total"),
        F.coalesce(F.col("VAL_UTI").cast("double"), F.lit(0.0)).alias("valor_uti"),
        F.coalesce(F.col("VAL_SH").cast("double"), F.lit(0.0)).alias("valor_serv_hospitalares"),
        F.coalesce(F.col("VAL_SP").cast("double"), F.lit(0.0)).alias("valor_serv_profissionais"),
    )
)

print(f"Linhas lidas do bronze: {prata.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Idade normalizada e dimensão temporal

# COMMAND ----------

prata = (
    prata
    # COD_IDADE indica a unidade: 2 = dias, 3 = meses, 4 = anos.
    # Sem normalizar, um recém-nascido de 20 dias viraria "20 anos".
    .withColumn(
        "idade_anos",
        F.when(F.col("_cod_idade") == "4", F.col("_idade"))
         .when(F.col("_cod_idade") == "3", F.col("_idade") / 12)
         .when(F.col("_cod_idade") == "2", F.col("_idade") / 365)
         .otherwise(F.lit(0.0)))
    .withColumn("idade_anos",
                F.least(F.greatest(F.col("idade_anos"), F.lit(0.0)), F.lit(120.0)))
    .withColumn(
        "faixa_etaria",
        F.when(F.col("idade_anos") < 1, "< 1 ano")
         .when(F.col("idade_anos") < 5, "1-4")
         .when(F.col("idade_anos") < 15, "5-14")
         .when(F.col("idade_anos") < 20, "15-19")
         .when(F.col("idade_anos") < 40, "20-39")
         .when(F.col("idade_anos") < 60, "40-59")
         .when(F.col("idade_anos") < 80, "60-79")
         .otherwise("80+"))

    # ---- Dimensão temporal DA ANÁLISE: data real de internação ----
    .withColumn("ano", F.year("dt_internacao"))
    .withColumn("mes", F.month("dt_internacao"))
    .withColumn("competencia", F.date_format("dt_internacao", "yyyyMM"))
    .withColumn("competencia_processamento",
                F.concat(F.col("ano_processamento").cast("string"),
                         F.lpad(F.col("mes_processamento").cast("string"), 2, "0")))
    # Defasagem em meses entre internar e ser faturado. É a métrica que
    # justifica ingerir competências até M+3 e permite auditar a cobertura.
    .withColumn("defasagem_faturamento",
                (F.col("ano_processamento") - F.col("ano")) * 12
                + (F.col("mes_processamento") - F.col("mes")))
    .drop("_idade", "_cod_idade")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Enriquecimento — capítulo CID, desfecho e sinalizadores

# COMMAND ----------

prata = (
    prata
    .withColumn("_cid3", F.substring(F.col("cid_principal"), 1, 3))
    .join(F.broadcast(dim_cid),
          (F.col("_cid3") >= F.col("cid_inicio")) & (F.col("_cid3") <= F.col("cid_fim")),
          "left")
    .drop("_cid3", "cid_inicio", "cid_fim")
    .withColumn("perfil_atendimento",
                F.coalesce(F.col("perfil_atendimento"), F.lit("Nao classificado")))

    .withColumn("_cod_saida_num", F.col("cod_motivo_saida").cast("int"))
    .join(F.broadcast(dim_desfecho),
          (F.col("_cod_saida_num") >= F.col("cod_inicio"))
          & (F.col("_cod_saida_num") <= F.col("cod_fim")),
          "left")
    .drop("_cod_saida_num", "cod_inicio", "cod_fim")
    .withColumn("desfecho", F.coalesce(F.col("desfecho"), F.lit("Nao informado")))

    # Sinalizadores derivados, usados direto nas agregações da camada Ouro.
    .withColumn("transferido", (F.col("desfecho") == "Transferencia").cast("int"))
    .withColumn("longa_permanencia",
                (F.col("tipo_aih") == "Longa permanencia").cast("int"))
    .withColumn("tem_comorbidade",
                ((F.length(F.col("cid_secundario")) >= 3)
                 & (~F.col("cid_secundario").isin("0000", "000", ""))).cast("int"))
    .withColumn("proc_alterado",
                (F.col("proc_solicitado") != F.col("procedimento")).cast("int"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Qualidade — deduplicação e regras de consistência
# MAGIC
# MAGIC A mesma AIH pode aparecer em mais de uma competência quando é
# MAGIC reapresentada. Deduplicamos por `n_aih` mantendo a apresentação mais
# MAGIC recente, que é a versão válida do registro.

# COMMAND ----------

from pyspark.sql import Window

antes = prata.count()

janela = Window.partitionBy("n_aih").orderBy(
    F.col("competencia_processamento").desc())

prata_limpa = (
    prata
    .withColumn("_ordem", F.row_number().over(janela))
    .filter(F.col("_ordem") == 1)
    .drop("_ordem")
    .filter(F.col("dt_internacao").isNotNull())
    .filter(F.col("dias_permanencia").between(0, 365))
    .filter(F.col("valor_total") >= 0)
    .withColumn("_processado_em", F.current_timestamp())
)

depois = prata_limpa.count()
print(f"Registros: {antes:,} -> {depois:,} "
      f"({100 * (antes - depois) / antes:.2f}% descartados)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Gravação

# COMMAND ----------

(prata_limpa.write
 .mode("overwrite").option("overwriteSchema", "true")
 .partitionBy("uf", "ano")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_PRATA}.internacoes"))

spark.sql(f"""
    COMMENT ON TABLE {CATALOGO}.{SCHEMA_PRATA}.internacoes IS
    'Internacoes do SIH/SUS limpas, tipadas e decodificadas. A dimensao temporal (ano, mes, competencia) vem da DATA DE INTERNACAO, nao da competencia de pagamento. Inclui capitulo CID-10 como perfil de atendimento e desfecho da internacao (alta, transferencia, obito).'
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Estabelecimentos, leitos e municípios

# COMMAND ----------

estabelecimentos = (
    spark.table(f"{CATALOGO}.{SCHEMA_BRONZE}.cnes_estabelecimentos")
    .select(
        F.lpad(F.trim(F.col("codigo_cnes").cast("string")), 7, "0").alias("cnes"),
        F.trim(F.coalesce(F.col("nome_fantasia"), F.col("nome_razao_social"),
                          F.lit("Nao informado"))).alias("nome_fantasia"),
        F.trim(F.col("codigo_municipio").cast("string")).alias("cod_municipio_6"),
        F.col("uf_consulta").alias("uf"),
        F.coalesce(F.col("descricao_esfera_administrativa"),
                   F.lit("Nao informada")).alias("esfera"),
        F.col("codigo_tipo_unidade").cast("int").alias("cod_tipo_unidade"),
        F.coalesce(F.col("estabelecimento_possui_atendimento_hospitalar").cast("int"),
                   F.lit(0)).alias("tem_atendimento_hospitalar"),
        F.coalesce(F.col("estabelecimento_possui_centro_cirurgico").cast("int"),
                   F.lit(0)).alias("tem_centro_cirurgico"),
        F.col("latitude_estabelecimento_decimo_grau").cast("double").alias("latitude"),
        F.col("longitude_estabelecimento_decimo_grau").cast("double").alias("longitude"),
    )
    .dropDuplicates(["cnes"])
)

(estabelecimentos.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_PRATA}.estabelecimentos"))

print(f"Estabelecimentos: {estabelecimentos.count():,}")

# COMMAND ----------

leitos = (
    spark.table(f"{CATALOGO}.{SCHEMA_BRONZE}.cnes_leitos")
    .select(
        F.lpad(F.trim(F.col("CNES")), 7, "0").alias("cnes"),
        F.trim(F.col("CODUFMUN")).alias("cod_municipio_6"),
        F.col("UF").alias("uf"),
        F.coalesce(F.col("QT_EXIST").cast("int"), F.lit(0)).alias("leitos_existentes"),
        F.coalesce(F.col("QT_SUS").cast("int"), F.lit(0)).alias("leitos_sus"),
    )
    .groupBy("cnes", "cod_municipio_6", "uf")
    .agg(F.sum("leitos_existentes").alias("leitos_existentes"),
         F.sum("leitos_sus").alias("leitos_sus"))
)

(leitos.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_PRATA}.leitos"))

print(f"Estabelecimentos com leito: {leitos.count():,}")
print(f"Leitos SUS no Sudeste     : {leitos.agg(F.sum('leitos_sus')).first()[0]:,}")

# COMMAND ----------

municipios = (
    spark.table(f"{CATALOGO}.{SCHEMA_BRONZE}.ibge_municipios")
    .select(
        F.lpad(F.col("cod_municipio_6").cast("string"), 6, "0").alias("cod_municipio_6"),
        F.col("cod_municipio").cast("string").alias("cod_municipio"),
        F.col("municipio"), F.col("uf"), F.col("uf_nome"), F.col("regiao"),
        F.col("populacao").cast("int").alias("populacao"),
        F.col("porte"),
        F.col("meta_leitos_oms").cast("int").alias("meta_leitos_oms"),
    )
    .dropDuplicates(["cod_municipio_6"])
)

(municipios.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{CATALOGO}.{SCHEMA_PRATA}.municipios"))

print(f"Municipios: {municipios.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Validação — a prova de que a correção temporal funcionou
# MAGIC
# MAGIC Se a dimensão temporal estivesse errada, janeiro apareceria inflado e a
# MAGIC defasagem de faturamento seria sempre zero. As duas consultas abaixo
# MAGIC devem mostrar o contrário.

# COMMAND ----------

display(spark.sql(f"""
    SELECT defasagem_faturamento                                     AS meses_ate_faturar,
           COUNT(*)                                                  AS internacoes,
           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)        AS percentual
      FROM {CATALOGO}.{SCHEMA_PRATA}.internacoes
     WHERE defasagem_faturamento BETWEEN 0 AND 6
     GROUP BY defasagem_faturamento
     ORDER BY defasagem_faturamento
"""))

# COMMAND ----------

display(spark.sql(f"""
    SELECT ano,
           COUNT(*)                                       AS internacoes,
           ROUND(AVG(dias_permanencia), 2)                AS permanencia_media,
           ROUND(100.0 * AVG(transferido), 2)             AS taxa_transferencia,
           ROUND(100.0 * AVG(obito), 2)                   AS taxa_mortalidade
      FROM {CATALOGO}.{SCHEMA_PRATA}.internacoes
     GROUP BY ano
     ORDER BY ano
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Leitura esperada
# MAGIC
# MAGIC - **Defasagem**: distribuição decrescente a partir de 0, com a maior
# MAGIC   parte concentrada nos três primeiros meses. Confirma que competência e
# MAGIC   internação são coisas diferentes.
# MAGIC - **Por ano**: aparecem 2023, 2024 e 2025. Só 2024 está completo — os
# MAGIC   outros dois são as caudas das competências das pontas e serão
# MAGIC   descartados na camada Ouro.
# MAGIC
# MAGIC ### Próximo passo
# MAGIC
# MAGIC O notebook `03_ouro` monta o star schema, calcula o indicador de pressão
# MAGIC assistencial e exporta as tabelas para o painel e para o Oracle.
