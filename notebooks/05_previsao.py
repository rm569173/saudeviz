# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Previsão de demanda hospitalar
# MAGIC
# MAGIC **Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173**
# MAGIC
# MAGIC **Objetivo de negócio:** estimar quantas internações cada UF terá nos
# MAGIC próximos meses, para a secretaria dimensionar leito, equipe e orçamento
# MAGIC **antes** da pressão acontecer.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Dois modelos, dois papéis
# MAGIC
# MAGIC | Modelo | Papel | Resultado |
# MAGIC |---|---|---|
# MAGIC | **Perfil semanal + fator de feriado** | **Prever** | MAPE 5,5% a 6,3% de 7 a 90 dias |
# MAGIC | **Regressão linear decomposta** | **Explicar** | MAPE 27% em 90 dias — reprovado como preditor |
# MAGIC
# MAGIC O melhor modelo explicativo não foi o melhor preditivo, e este notebook
# MAGIC mostra as duas coisas em vez de escolher a narrativa mais conveniente.
# MAGIC
# MAGIC ## Como chegamos aqui
# MAGIC
# MAGIC Três erros foram encontrados e corrigidos durante a modelagem. Estão
# MAGIC registrados porque o processo importa tanto quanto o resultado:
# MAGIC
# MAGIC 1. **Modelo mensal com zero graus de liberdade.** A primeira versão usava
# MAGIC    tendência mais 11 dummies de mês sobre 12 observações por UF — 12
# MAGIC    parâmetros para 12 pontos. Trocamos para série diária (366 pontos).
# MAGIC 2. **Dummy de dezembro estimada com uma observação.** Na validação
# MAGIC    temporal, o treino terminava em 1º de dezembro, e `mes_12` aparecia em
# MAGIC    um único dia. Trocamos dummies mensais por termos de Fourier.
# MAGIC 3. **Baseline com vazamento de dados.** A baseline usava `shift(7)`, que
# MAGIC    dentro da janela de teste consulta valores reais que ela não deveria
# MAGIC    conhecer. Substituída por perfil calculado apenas com dados anteriores
# MAGIC    ao corte.
# MAGIC
# MAGIC O erro do modelo caiu de 51% para 8% com as duas primeiras correções — e
# MAGIC a terceira revelou que, mesmo assim, a abordagem simples era melhor.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOGO = "workspace"
SCHEMA_PRATA = "saudeviz_prata"
SCHEMA_OURO = "saudeviz_ouro"
ANO_ANALISE = 2024

HORIZONTE_TESTE = 30   # dias avaliados em cada fold
DIAS_PREVISAO = 90     # horizonte projetado
JANELA_PERFIL = 28     # dias usados para estimar o perfil semanal

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Série diária de internações
# MAGIC
# MAGIC Construída pela data real de internação, não pela competência de
# MAGIC pagamento.

# COMMAND ----------

import numpy as np
import pandas as pd

serie = (
    spark.table(f"{CATALOGO}.{SCHEMA_PRATA}.internacoes")
    .filter(F.col("ano") == ANO_ANALISE)
    .groupBy("uf", "dt_internacao")
    .agg(F.count("*").alias("internacoes"),
         F.sum("dias_permanencia").alias("dias_permanencia"),
         F.sum("valor_total").alias("valor_total"),
         F.sum("transferido").alias("transferencias"))
    .orderBy("uf", "dt_internacao")
    .toPandas()
)

serie["dt_internacao"] = pd.to_datetime(serie["dt_internacao"])
serie["dia_semana"] = serie["dt_internacao"].dt.dayofweek   # 0 = segunda
serie["mes"] = serie["dt_internacao"].dt.month

NOMES_DIA = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]

# Feriados nacionais de 2024 e recesso de fim de ano. O efeito do Natal sobre a
# internação eletiva não é "dezembro": são dias específicos.
FERIADOS = pd.to_datetime([
    "2024-01-01",                              # Confraternizacao Universal
    "2024-02-12", "2024-02-13", "2024-02-14",  # Carnaval e quarta de cinzas
    "2024-03-29",                              # Sexta-feira Santa
    "2024-04-21",                              # Tiradentes
    "2024-05-01",                              # Dia do Trabalho
    "2024-05-30",                              # Corpus Christi
    "2024-09-07",                              # Independencia
    "2024-10-12",                              # Nossa Senhora Aparecida
    "2024-11-02",                              # Finados
    "2024-11-15",                              # Proclamacao da Republica
    "2024-11-20",                              # Consciencia Negra
    "2024-12-24", "2024-12-25",                # Vespera e Natal
    "2024-12-31",                              # Vespera de Ano Novo
])
serie["feriado"] = serie["dt_internacao"].isin(FERIADOS).astype(int)

print(f"Serie diaria: {len(serie):,} linhas | {serie['uf'].nunique()} UFs")
display(serie.groupby("uf")["internacoes"]
        .agg(["count", "sum", "mean"]).round(0).reset_index())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. O padrão que a agregação mensal escondia

# COMMAND ----------

por_dia = (serie[serie["feriado"] == 0]
           .groupby("dia_semana")["internacoes"].mean().reset_index())
por_dia["dia"] = por_dia["dia_semana"].map(dict(enumerate(NOMES_DIA)))
por_dia["indice"] = (por_dia["internacoes"] / por_dia["internacoes"].mean()).round(3)
display(por_dia[["dia", "internacoes", "indice"]])

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** a queda de fim de semana não é falta de
# MAGIC doente — é a rede eletiva parada. Urgência não escolhe dia. A distância
# MAGIC entre o pico de segunda e o vale de domingo mede quanto da operação é
# MAGIC programável, e portanto **remanejável**.
# MAGIC
# MAGIC Esse padrão importa mais para o planejamento de escala do que a
# MAGIC sazonalidade mensal, que é fraca (±8%).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Modelo preditivo — perfil semanal com ajuste de feriado
# MAGIC
# MAGIC ```
# MAGIC previsão(dia) = média do mesmo dia da semana nos últimos 28 dias úteis
# MAGIC                 × fator de feriado, se o dia for feriado
# MAGIC ```
# MAGIC
# MAGIC Dois parâmetros por UF: o perfil de sete dias e um fator de feriado.
# MAGIC Simples de propósito — e, como a validação mostra, mais preciso que a
# MAGIC regressão em todos os horizontes.

# COMMAND ----------

def perfil_semanal(historico: pd.DataFrame, janela: int = JANELA_PERFIL) -> pd.Series:
    """Média de internações por dia da semana, ignorando feriados."""
    normais = historico[historico["feriado"] == 0]
    recente = normais.iloc[-janela:]
    perfil = recente.groupby("dia_semana")["internacoes"].mean()
    # Se a janela recente não cobrir os sete dias, recorre ao histórico inteiro.
    if len(perfil) < 7:
        perfil = normais.groupby("dia_semana")["internacoes"].mean()
    return perfil


def fator_feriado(historico: pd.DataFrame) -> float:
    """
    Quanto um feriado reduz a demanda frente ao mesmo dia da semana normal.

    Calculado como a razão média entre o observado no feriado e o esperado
    pelo perfil daquele dia da semana.
    """
    feriados = historico[historico["feriado"] == 1]
    if feriados.empty:
        return 1.0
    normal = (historico[historico["feriado"] == 0]
              .groupby("dia_semana")["internacoes"].mean())
    esperado = feriados["dia_semana"].map(normal)
    return float((feriados["internacoes"] / esperado).mean())


def preve(historico: pd.DataFrame, datas: pd.DatetimeIndex) -> np.ndarray:
    """Aplica perfil semanal e ajuste de feriado às datas informadas."""
    perfil = perfil_semanal(historico)
    fator = fator_feriado(historico)
    dias_semana = pd.Series(datas.dayofweek, index=range(len(datas)))
    base = dias_semana.map(perfil).values
    eh_feriado = pd.Series(datas).isin(FERIADOS).values
    return base * np.where(eh_feriado, fator, 1.0)


display(pd.DataFrame([
    {"uf": uf, "fator_feriado": round(fator_feriado(g), 3),
     "reducao_pct": round(100 * (1 - fator_feriado(g)), 1)}
    for uf, g in serie.groupby("uf")
]))

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura:** o fator é consistente entre os quatro estados — um feriado
# MAGIC reduz as internações em torno de um quarto. Consistência entre unidades
# MAGIC independentes é indício de que o parâmetro captura um fenômeno real, e
# MAGIC não ruído de uma série específica.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Modelo explicativo — regressão decomposta
# MAGIC
# MAGIC Não é o preditor final. Serve para **quantificar** cada componente:
# MAGIC quanto pesa o dia da semana, quanto pesa o feriado, se há tendência.

# COMMAND ----------

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

PERIODO_ANUAL = 365.25


def monta_features(df: pd.DataFrame, inicio: pd.Timestamp) -> pd.DataFrame:
    """
    Tendência + dia da semana + sazonalidade em Fourier + feriado.

    A sazonalidade usa seno e cosseno em vez de dummies mensais: numa
    validação temporal, a dummy do último mês seria estimada com pouquíssimas
    observações e o coeficiente absorveria o resíduo desses poucos dias.
    """
    dias = (df["dt_internacao"] - inicio).dt.days
    x = pd.DataFrame(index=df.index)
    x["tendencia"] = dias
    for dia in range(1, 7):                       # segunda-feira e a referencia
        x[f"dia_{NOMES_DIA[dia]}"] = (df["dia_semana"] == dia).astype(int)
    for harmonico in (1, 2):                      # ciclo anual e semestral
        angulo = 2 * np.pi * harmonico * dias / PERIODO_ANUAL
        x[f"sazonal_sen{harmonico}"] = np.sin(angulo)
        x[f"sazonal_cos{harmonico}"] = np.cos(angulo)
    x["feriado"] = df["dt_internacao"].isin(FERIADOS).astype(int)
    return x


coeficientes = []
for uf, grupo in serie.groupby("uf"):
    grupo = grupo.sort_values("dt_internacao").reset_index(drop=True)
    inicio = grupo["dt_internacao"].min()
    x = monta_features(grupo, inicio)
    # Escala logarítmica: contagens são multiplicativas, e o log estabiliza a
    # variância entre UFs de tamanhos muito diferentes.
    modelo = LinearRegression().fit(x, np.log(grupo["internacoes"].clip(lower=1)))
    for nome, valor in zip(x.columns, modelo.coef_):
        coeficientes.append({
            "uf": uf,
            "variavel": nome,
            "efeito_pct": round(100 * (np.exp(valor) - 1), 2),
        })

df_coef = pd.DataFrame(coeficientes)
display(df_coef[df_coef["variavel"].str.startswith(("dia_", "feriado"))]
        .pivot(index="variavel", columns="uf", values="efeito_pct"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Como ler:** os valores estão em **variação percentual** frente à
# MAGIC segunda-feira, porque o modelo foi ajustado em escala logarítmica. Um
# MAGIC efeito de −40% em domingo significa 40% menos internações que numa
# MAGIC segunda equivalente, mantendo o resto constante.
# MAGIC
# MAGIC É esta tabela — e não a previsão — que responde à frente de
# MAGIC **explicabilidade** do desafio.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Validação — janela expansível, com baseline honesta
# MAGIC
# MAGIC Cinco cortes temporais por UF, sempre treinando no passado e medindo no
# MAGIC futuro. Nenhum modelo enxerga dado posterior ao seu corte.

# COMMAND ----------

CORTES = [216, 246, 276, 306, 336]

resultados, detalhe = [], []
for uf, grupo in serie.groupby("uf"):
    grupo = grupo.sort_values("dt_internacao").reset_index(drop=True)
    inicio = grupo["dt_internacao"].min()
    erros_perfil, erros_regressao = [], []

    for corte in CORTES:
        treino = grupo.iloc[:corte]
        teste = grupo.iloc[corte:corte + HORIZONTE_TESTE]
        if len(teste) < HORIZONTE_TESTE:
            continue

        datas_teste = pd.DatetimeIndex(teste["dt_internacao"])
        prev_perfil = preve(treino, datas_teste)

        modelo = LinearRegression().fit(
            monta_features(treino, inicio),
            np.log(treino["internacoes"].clip(lower=1)))
        prev_regressao = np.exp(modelo.predict(monta_features(teste, inicio)))

        mape_perfil = 100 * mean_absolute_percentage_error(
            teste["internacoes"], prev_perfil)
        mape_regressao = 100 * mean_absolute_percentage_error(
            teste["internacoes"], prev_regressao)

        erros_perfil.append(
            (mean_absolute_error(teste["internacoes"], prev_perfil), mape_perfil))
        erros_regressao.append(
            (mean_absolute_error(teste["internacoes"], prev_regressao),
             mape_regressao))
        detalhe.append({"uf": uf,
                        "treino_ate": treino["dt_internacao"].max().date(),
                        "mape_perfil": round(mape_perfil, 2),
                        "mape_regressao": round(mape_regressao, 2)})

    resultados.append({
        "uf": uf,
        "folds": len(erros_perfil),
        "mae_perfil": np.mean([e[0] for e in erros_perfil]),
        "mape_perfil": np.mean([e[1] for e in erros_perfil]),
        "mae_regressao": np.mean([e[0] for e in erros_regressao]),
        "mape_regressao": np.mean([e[1] for e in erros_regressao]),
    })

avaliacao = pd.DataFrame(resultados).round(2)
avaliacao["modelo_escolhido"] = np.where(
    avaliacao["mape_perfil"] <= avaliacao["mape_regressao"],
    "Perfil semanal", "Regressao")
display(avaliacao)

# COMMAND ----------

display(pd.DataFrame(detalhe))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Desempenho por horizonte — o teste decisivo
# MAGIC
# MAGIC Um modelo pode ser bom em uma semana e inútil em três meses. Como o
# MAGIC objetivo de negócio é planejar leito e orçamento com antecedência, é o
# MAGIC horizonte longo que importa.

# COMMAND ----------

comparativo = []
for horizonte in (7, 15, 30, 60, 90):
    cortes = list(range(180, 366 - horizonte, 30))
    perfis, regressoes = [], []
    for uf, grupo in serie.groupby("uf"):
        grupo = grupo.sort_values("dt_internacao").reset_index(drop=True)
        inicio = grupo["dt_internacao"].min()
        for corte in cortes:
            treino = grupo.iloc[:corte]
            teste = grupo.iloc[corte:corte + horizonte]
            if len(teste) < horizonte:
                continue
            datas_teste = pd.DatetimeIndex(teste["dt_internacao"])
            perfis.append(100 * mean_absolute_percentage_error(
                teste["internacoes"], preve(treino, datas_teste)))
            modelo = LinearRegression().fit(
                monta_features(treino, inicio),
                np.log(treino["internacoes"].clip(lower=1)))
            regressoes.append(100 * mean_absolute_percentage_error(
                teste["internacoes"],
                np.exp(modelo.predict(monta_features(teste, inicio)))))
    comparativo.append({
        "horizonte_dias": horizonte,
        "mape_perfil": round(np.mean(perfis), 2),
        "mape_regressao": round(np.mean(regressoes), 2),
    })

df_horizonte = pd.DataFrame(comparativo)
df_horizonte["vencedor"] = np.where(
    df_horizonte["mape_perfil"] <= df_horizonte["mape_regressao"],
    "Perfil semanal", "Regressao")
display(df_horizonte)

# COMMAND ----------

# MAGIC %md
# MAGIC **Este é o gráfico que justifica a escolha do modelo.** O erro da
# MAGIC regressão cresce com o horizonte porque a tendência linear extrapola: um
# MAGIC coeficiente diário pequeno vira desvio grande em 90 dias. O perfil
# MAGIC semanal permanece estável.
# MAGIC
# MAGIC **Conclusão técnica:** a série de internações do Sudeste **não tem
# MAGIC tendência nem sazonalidade anual exploráveis** para previsão. O sinal
# MAGIC previsível está no ciclo semanal e nos feriados. Reconhecer isso vale
# MAGIC mais que forçar um modelo complexo sobre um fenômeno que não o comporta.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Projeção para os próximos 90 dias

# COMMAND ----------

projecoes = []
for uf, grupo in serie.groupby("uf"):
    grupo = grupo.sort_values("dt_internacao").reset_index(drop=True)

    ajuste = preve(grupo, pd.DatetimeIndex(grupo["dt_internacao"]))
    residuo_std = float(np.std(grupo["internacoes"] - ajuste))

    historico = pd.DataFrame({
        "uf": uf,
        "data": grupo["dt_internacao"],
        "internacoes_reais": grupo["internacoes"].astype(float),
        "internacoes_previstas": np.round(ajuste).astype(int),
        "tipo": "historico",
    })

    datas_futuras = pd.date_range(
        grupo["dt_internacao"].max() + pd.Timedelta(days=1),
        periods=DIAS_PREVISAO, freq="D")
    futuro = pd.DataFrame({
        "uf": uf,
        "data": datas_futuras,
        "internacoes_reais": np.nan,
        "internacoes_previstas": np.round(preve(grupo, datas_futuras)).astype(int),
        "tipo": "previsao",
    })

    parcial = pd.concat([historico, futuro], ignore_index=True)
    parcial["limite_inferior"] = np.maximum(
        parcial["internacoes_previstas"] - 1.96 * residuo_std, 0).round().astype(int)
    parcial["limite_superior"] = (
        parcial["internacoes_previstas"] + 1.96 * residuo_std).round().astype(int)
    parcial["mape_validacao"] = float(
        avaliacao.loc[avaliacao["uf"] == uf, "mape_perfil"].iloc[0])
    projecoes.append(parcial)

previsao = pd.concat(projecoes, ignore_index=True)
previsao["competencia"] = previsao["data"].dt.strftime("%Y%m")

display(previsao[previsao["tipo"] == "previsao"]
        .groupby(["uf", "competencia"])["internacoes_previstas"]
        .sum().reset_index())

# COMMAND ----------

# MAGIC %md
# MAGIC ⚠️ **Ressalvas que precisam constar na apresentação:**
# MAGIC
# MAGIC 1. As internações de dezembro/2024 têm cobertura de ~99,4%: as faturadas
# MAGIC    a partir de abril/2025 não entraram na ingestão. O fim da série está
# MAGIC    levemente subestimado.
# MAGIC 2. O calendário de feriados usado é o de 2024. Para projetar 2025 em
# MAGIC    produção, o calendário do ano corrente precisa ser carregado.
# MAGIC 3. O modelo não conhece eventos excepcionais — surto epidêmico, greve,
# MAGIC    desastre. Ele projeta a rotina, e é assim que deve ser lido.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Gravação na camada Ouro

# COMMAND ----------

TABELAS_NOVAS = {
    "previsao_internacoes": previsao[
        ["uf", "data", "competencia", "internacoes_reais", "internacoes_previstas",
         "limite_inferior", "limite_superior", "tipo", "mape_validacao"]],
    "avaliacao_modelo": avaliacao,
    "comparativo_horizonte": df_horizonte,
    "coeficientes_modelo": df_coef,
    "serie_diaria_uf": serie.rename(columns={"dt_internacao": "data"})[
        ["uf", "data", "internacoes", "dias_permanencia", "valor_total",
         "transferencias", "dia_semana", "mes", "feriado"]],
}

for nome, df in TABELAS_NOVAS.items():
    (spark.createDataFrame(df).write.mode("overwrite")
     .option("overwriteSchema", "true")
     .saveAsTable(f"{CATALOGO}.{SCHEMA_OURO}.{nome}"))
    print(f"{nome:26s} {len(df):>8,} linhas")

# COMMAND ----------

VOLUME_SAIDA = f"/Volumes/{CATALOGO}/saudeviz/landing/ouro"

for nome in TABELAS_NOVAS:
    df = spark.table(f"{CATALOGO}.{SCHEMA_OURO}.{nome}")
    df.coalesce(1).write.mode("overwrite").parquet(f"{VOLUME_SAIDA}/{nome}")
    print(f"{nome:26s} exportado")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Carga no Oracle

# COMMAND ----------

# MAGIC %pip install oracledb --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import time

import oracledb
from pyspark.sql import types as T

CATALOGO = "workspace"
SCHEMA_OURO = "saudeviz_ouro"
PREFIXO = "T_SAUDE_"
LOTE = 10_000

USUARIO = dbutils.secrets.get("saudeviz", "oracle_user")
SENHA = dbutils.secrets.get("saudeviz", "oracle_password")
DSN = dbutils.secrets.get("saudeviz", "oracle_dsn")

COMENTARIOS = {
    "previsao_internacoes":
        "Previsao diaria de internacoes por UF pelo modelo de perfil semanal com ajuste de feriado. tipo indica historico ajustado ou projecao futura. limite_inferior e limite_superior formam intervalo de 95 por cento.",
    "avaliacao_modelo":
        "Metricas de validacao por UF em janela expansivel de cinco cortes, comparando o modelo de perfil semanal contra a regressao decomposta.",
    "comparativo_horizonte":
        "Erro medio percentual de cada modelo por horizonte de previsao, de 7 a 90 dias. Mostra a degradacao da regressao no longo prazo.",
    "coeficientes_modelo":
        "Efeito percentual de cada variavel do modelo explicativo sobre o numero de internacoes, por UF. Responde quanto pesa cada dia da semana e o feriado.",
    "serie_diaria_uf":
        "Serie diaria de internacoes por UF pela data real de internacao, com marcacao de dia da semana e feriado.",
}

conexao = oracledb.connect(user=USUARIO, password=SENHA, dsn=DSN)
try:
    with conexao.cursor() as cursor:
        for tabela, comentario in COMENTARIOS.items():
            df = spark.table(f"{CATALOGO}.{SCHEMA_OURO}.{tabela}")
            nome_oracle = f"{PREFIXO}{tabela.upper()}"
            inicio = time.time()

            def tipo_oracle(campo):
                tipo = campo.dataType
                if isinstance(tipo, (T.IntegerType, T.LongType, T.ShortType,
                                     T.ByteType)):
                    return "NUMBER(18)"
                if isinstance(tipo, (T.DoubleType, T.FloatType, T.DecimalType)):
                    return "NUMBER(20, 4)"
                if isinstance(tipo, T.DateType):
                    return "DATE"
                if isinstance(tipo, T.TimestampType):
                    return "TIMESTAMP"
                return "VARCHAR2(300)"

            colunas_ddl = ",\n    ".join(
                f"{c.name} {tipo_oracle(c)}" for c in df.schema.fields)
            cursor.execute(f"""
                BEGIN EXECUTE IMMEDIATE 'DROP TABLE {nome_oracle}';
                EXCEPTION WHEN OTHERS THEN NULL; END;
            """)
            cursor.execute(f"CREATE TABLE {nome_oracle} (\n    {colunas_ddl}\n)")
            cursor.execute(f"COMMENT ON TABLE {nome_oracle} IS "
                           f"'{comentario.replace(chr(39), chr(39) * 2)}'")

            pdf = df.toPandas()
            pdf = pdf.astype(object).where(pdf.notna(), None)
            marcadores = ", ".join(f":{i + 1}" for i in range(len(pdf.columns)))
            insert = (f"INSERT INTO {nome_oracle} ({', '.join(pdf.columns)}) "
                      f"VALUES ({marcadores})")
            linhas = list(pdf.itertuples(index=False, name=None))
            for i in range(0, len(linhas), LOTE):
                cursor.executemany(insert, linhas[i:i + LOTE])
                conexao.commit()
            print(f"{nome_oracle:34s} {len(linhas):>8,} linhas "
                  f"em {time.time() - inicio:5.1f}s")
finally:
    conexao.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Próximos passos
# MAGIC
# MAGIC 1. `py -m src.db.databricks_upload --baixar-ouro`
# MAGIC 2. Motor NL→SQL sobre os `COMMENT ON` das tabelas `T_SAUDE_*`
# MAGIC 3. Painel Streamlit consultando o Oracle ao vivo
