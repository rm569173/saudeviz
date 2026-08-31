# Databricks notebook source
# MAGIC %md
# MAGIC # SaúdeViz — Análise Exploratória de Dados
# MAGIC
# MAGIC **Challenge FIAP × Oracle 2026 · 1TSCOA · Lucas Ventura Araujo Ribas Colen — RM 569173**
# MAGIC
# MAGIC Cada seção abaixo é uma **pergunta de negócio**, a **consulta SQL** que a
# MAGIC responde e a **leitura do resultado**. As consultas rodam contra a camada
# MAGIC Ouro — as mesmas tabelas `T_SAUDE_*` que estão no Oracle Database.
# MAGIC
# MAGIC ## Cobertura das quatro frentes analíticas do desafio
# MAGIC
# MAGIC | Frente pedida pela Oracle | Onde está |
# MAGIC |---|---|
# MAGIC | 1. Exploração inicial — sazonalidade, rankings, comparações | Q3 a Q7 |
# MAGIC | 2. Indicadores de capacidade — pressão assistencial | Q10 a Q12 |
# MAGIC | 3. Padrões e agrupamentos | Q13 a Q15 |
# MAGIC | 4. Explicabilidade — traduzir para linguagem de gestão | Leitura de cada bloco |
# MAGIC
# MAGIC ## Recorte
# MAGIC
# MAGIC Região Sudeste (ES, MG, RJ, SP), internações **ocorridas** em 2024.
# MAGIC 5.546.817 internações, 3.131 estabelecimentos com leito, 1.668 municípios.

# COMMAND ----------

# MAGIC %md
# MAGIC > **Nota sobre os nomes das tabelas:** todas as consultas usam o nome
# MAGIC > completo `workspace.saudeviz_ouro.<tabela>`. No compute serverless o
# MAGIC > `USE SCHEMA` nao persiste entre celulas, e qualificar tambem deixa
# MAGIC > cada consulta autossuficiente para quem for reproduzi-la.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Bloco 1 — Entendimento e qualidade do dado
# MAGIC
# MAGIC Antes de analisar, provar que o dado é o que dizemos que é.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q1. As três fontes chegaram completas?
# MAGIC
# MAGIC **Pergunta:** o desafio exige tabela relacional, JSON e CSV. Os três
# MAGIC formatos foram integrados e conversam entre si?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT 'Fonte 1 - SIH/SUS (relacional)'  AS fonte,
# MAGIC        'FTP DATASUS, arquivos .dbc'      AS origem,
# MAGIC        SUM(internacoes) AS registros
# MAGIC   FROM workspace.saudeviz_ouro.fato_internacao_mensal
# MAGIC UNION ALL
# MAGIC SELECT 'Fonte 2 - CNES (JSON via API)',
# MAGIC        'apidadosabertos.saude.gov.br',
# MAGIC        COUNT(*)
# MAGIC   FROM workspace.saudeviz_ouro.dim_estabelecimento
# MAGIC UNION ALL
# MAGIC SELECT 'Fonte 3 - IBGE (CSV)',
# MAGIC        'servicodados.ibge.gov.br',
# MAGIC        COUNT(*)
# MAGIC   FROM workspace.saudeviz_ouro.dim_municipio;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q2. A integração entre as fontes funciona?
# MAGIC
# MAGIC **Pergunta:** de nada adianta ter três formatos se eles não se cruzam. O
# MAGIC SIH liga no CNES pelo código do estabelecimento, e ambos ligam no IBGE
# MAGIC pelo código do município. Quanto da base efetivamente casa?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC     COUNT(*)                                                    AS hospitais_no_sih,
# MAGIC     SUM(CASE WHEN e.cnes IS NOT NULL THEN 1 ELSE 0 END)         AS casaram_com_cnes,
# MAGIC     ROUND(100.0 * SUM(CASE WHEN e.cnes IS NOT NULL THEN 1 ELSE 0 END)
# MAGIC           / COUNT(*), 1)                                        AS pct_integracao,
# MAGIC     SUM(CASE WHEN m.cod_municipio_6 IS NOT NULL THEN 1 ELSE 0 END) AS casaram_com_ibge
# MAGIC   FROM workspace.saudeviz_ouro.rank_hospitais r
# MAGIC   LEFT JOIN workspace.saudeviz_ouro.dim_estabelecimento e ON r.cnes = e.cnes
# MAGIC   LEFT JOIN workspace.saudeviz_ouro.dim_municipio       m ON r.cod_municipio_6 = m.cod_municipio_6;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura:** a taxa de integração mede a qualidade do modelo dimensional.
# MAGIC Hospitais do SIH sem correspondência no CNES são, em geral, unidades
# MAGIC desativadas que ainda faturaram no período — comportamento esperado, e o
# MAGIC motivo de usarmos `LEFT JOIN` e não `INNER`: perder internação real por
# MAGIC falha de cadastro distorceria o volume.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Bloco 2 — Exploração inicial
# MAGIC
# MAGIC Sazonalidade, rankings e comparações entre municípios e hospitais.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q3. Existe sazonalidade nas internações?
# MAGIC
# MAGIC **Pergunta:** há meses de pico que justifiquem escalar equipe e leito?
# MAGIC
# MAGIC ⚠️ **Cuidado metodológico:** comparar totais mensais direto é errado —
# MAGIC fevereiro tem 29 dias e janeiro tem 31. A consulta normaliza por
# MAGIC **internações por dia**, e mostra os dois índices lado a lado para deixar
# MAGIC a diferença explícita.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH mensal AS (
# MAGIC     SELECT mes,
# MAGIC            SUM(internacoes)                                   AS internacoes,
# MAGIC            DAY(LAST_DAY(TO_DATE(CONCAT('2024-', LPAD(mes, 2, '0'), '-01')))) AS dias_no_mes
# MAGIC       FROM workspace.saudeviz_ouro.fato_internacao_mensal
# MAGIC      GROUP BY mes
# MAGIC ), com_taxa AS (
# MAGIC     SELECT mes, internacoes, dias_no_mes,
# MAGIC            internacoes / dias_no_mes AS internacoes_dia
# MAGIC       FROM mensal
# MAGIC )
# MAGIC SELECT mes,
# MAGIC        internacoes,
# MAGIC        dias_no_mes,
# MAGIC        ROUND(internacoes_dia, 0)                                        AS internacoes_por_dia,
# MAGIC        ROUND(internacoes     / AVG(internacoes)     OVER (), 3)         AS indice_bruto,
# MAGIC        ROUND(internacoes_dia / AVG(internacoes_dia) OVER (), 3)         AS indice_por_dia
# MAGIC   FROM com_taxa
# MAGIC  ORDER BY mes;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** a demanda hospitalar do Sudeste é **pouco
# MAGIC sazonal** — a amplitude fica em torno de ±8%. Isso é um achado, não uma
# MAGIC ausência de achado: significa que a pressão sobre o sistema é
# MAGIC **estrutural e permanente**, não um pico que passa. Planejamento de leito
# MAGIC não pode ser sazonal.
# MAGIC
# MAGIC O vale de dezembro e janeiro é o efeito de férias e adiamento de
# MAGIC cirurgias eletivas; o pico de abril é a retomada.
# MAGIC
# MAGIC 🚨 **Ressalva obrigatória:** dezembro tem cobertura de ~99,4%, porque
# MAGIC internações de dezembro faturadas a partir de abril/2025 não entraram na
# MAGIC ingestão. Parte da queda de dezembro é cobertura, não demanda.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q4. Como as UFs se comparam?
# MAGIC
# MAGIC **Pergunta:** qual estado do Sudeste está sob maior pressão, e onde o
# MAGIC paciente custa mais caro?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT uf,
# MAGIC        SUM(internacoes)                          AS internacoes,
# MAGIC        ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)          AS permanencia_media,
# MAGIC        ROUND(100.0 * SUM(obitos)         / SUM(internacoes), 2)    AS taxa_mortalidade,
# MAGIC        ROUND(100.0 * SUM(transferencias) / SUM(internacoes), 2)    AS taxa_transferencia,
# MAGIC        ROUND(SUM(valor_total) / SUM(internacoes), 2)               AS custo_medio_aih,
# MAGIC        ROUND(SUM(valor_total) / 1e9, 2)                            AS valor_total_bilhoes
# MAGIC   FROM workspace.saudeviz_ouro.fato_internacao_mensal
# MAGIC  GROUP BY uf
# MAGIC  ORDER BY internacoes DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q5. Onde as internações estão crescendo?
# MAGIC
# MAGIC **Pergunta direta do desafio.** Compara o segundo semestre contra o
# MAGIC primeiro, por município, filtrando volume mínimo para não ranquear ruído
# MAGIC de cidade pequena.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH semestres AS (
# MAGIC     SELECT c.cod_municipio_6,
# MAGIC            c.municipio,
# MAGIC            c.uf,
# MAGIC            c.populacao,
# MAGIC            SUM(CASE WHEN c.mes <= 6 THEN c.internacoes ELSE 0 END) AS sem1,
# MAGIC            SUM(CASE WHEN c.mes >  6 THEN c.internacoes ELSE 0 END) AS sem2
# MAGIC       FROM workspace.saudeviz_ouro.ind_capacidade_municipal c
# MAGIC      GROUP BY c.cod_municipio_6, c.municipio, c.uf, c.populacao
# MAGIC )
# MAGIC SELECT municipio,
# MAGIC        uf,
# MAGIC        populacao,
# MAGIC        sem1                                              AS internacoes_1o_sem,
# MAGIC        sem2                                              AS internacoes_2o_sem,
# MAGIC        ROUND(100.0 * (sem2 - sem1) / sem1, 1)            AS crescimento_pct
# MAGIC   FROM semestres
# MAGIC  WHERE sem1 >= 500          -- volume mínimo para o percentual ter sentido
# MAGIC  ORDER BY crescimento_pct DESC
# MAGIC  LIMIT 15;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** esta é a lista que um secretário estadual usaria
# MAGIC para decidir onde reforçar rede **antes** da próxima crise. O filtro de 500
# MAGIC internações no primeiro semestre é deliberado: sem ele, um município que
# MAGIC saiu de 2 para 6 internações apareceria com "crescimento de 200%" e
# MAGIC contaminaria a decisão.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q6. Quem são os maiores hospitais, e como operam?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ranking_regional                       AS pos,
# MAGIC        nome_fantasia,
# MAGIC        uf,
# MAGIC        esfera,
# MAGIC        internacoes,
# MAGIC        leitos_sus,
# MAGIC        permanencia_media,
# MAGIC        giro_leito_ano,
# MAGIC        taxa_mortalidade,
# MAGIC        taxa_transferencia,
# MAGIC        custo_medio_aih      AS custo_medio_aih
# MAGIC   FROM workspace.saudeviz_ouro.rank_hospitais
# MAGIC  ORDER BY ranking_regional
# MAGIC  LIMIT 20;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura:** o **giro de leito** (internações por leito no ano) separa
# MAGIC eficiência de tamanho. Dois hospitais com o mesmo número de leitos e giros
# MAGIC muito diferentes têm perfis assistenciais distintos — ou eficiências
# MAGIC distintas. É a pergunta que o gestor leva para a mesa.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Bloco 3 — Perfis de atendimento
# MAGIC
# MAGIC *"Quais tipos de atendimento estão pressionando mais o sistema?"*

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q7. Volume não é o mesmo que pressão
# MAGIC
# MAGIC **Pergunta:** qual perfil consome mais leito — e não apenas qual aparece
# MAGIC mais vezes?
# MAGIC
# MAGIC A métrica-chave é a **pressão relativa**: a participação do perfil nos
# MAGIC leitos-dia dividida pela participação no número de internações. Acima de
# MAGIC 1, o perfil ocupa mais leito do que o volume sugere.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH totais AS (
# MAGIC     SELECT SUM(internacoes)      AS total_internacoes,
# MAGIC            SUM(dias_permanencia) AS total_leitos_dia
# MAGIC       FROM workspace.saudeviz_ouro.fato_internacao_mensal
# MAGIC )
# MAGIC SELECT f.perfil_atendimento,
# MAGIC        SUM(f.internacoes)                               AS internacoes,
# MAGIC        ROUND(100.0 * SUM(f.internacoes)      / MAX(t.total_internacoes), 1) AS pct_internacoes,
# MAGIC        ROUND(100.0 * SUM(f.dias_permanencia) / MAX(t.total_leitos_dia), 1)  AS pct_leitos_dia,
# MAGIC        ROUND((SUM(f.dias_permanencia) / MAX(t.total_leitos_dia))
# MAGIC              / (SUM(f.internacoes)    / MAX(t.total_internacoes)), 2)       AS pressao_relativa,
# MAGIC        ROUND(SUM(f.dias_permanencia) / SUM(f.internacoes), 2)               AS permanencia_media,
# MAGIC        ROUND(SUM(f.valor_total)      / SUM(f.internacoes), 2)               AS custo_medio_aih
# MAGIC   FROM workspace.saudeviz_ouro.fato_internacao_mensal f
# MAGIC  CROSS JOIN totais t
# MAGIC  GROUP BY f.perfil_atendimento
# MAGIC  ORDER BY pressao_relativa DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão — este é um dos achados centrais do projeto.**
# MAGIC
# MAGIC Perfis com pressão relativa alta são invisíveis num painel que só conta
# MAGIC internações, mas são exatamente os que travam leito. **Saúde mental** é o
# MAGIC caso extremo: participação pequena no volume, participação várias vezes
# MAGIC maior nos leitos-dia, com permanência média muito acima das demais.
# MAGIC
# MAGIC Consequência prática: abrir leito clínico não resolve pressão psiquiátrica.
# MAGIC São redes diferentes, e o painel torna isso visível.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q8. Urgência e complexidade mudam a permanência?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT complexidade,
# MAGIC        carater_internacao,
# MAGIC        SUM(internacoes)                        AS internacoes,
# MAGIC        ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)        AS permanencia_media,
# MAGIC        ROUND(SUM(valor_total)      / SUM(internacoes), 2)        AS custo_medio_aih,
# MAGIC        ROUND(100.0 * SUM(obitos)   / SUM(internacoes), 2)        AS taxa_mortalidade
# MAGIC   FROM workspace.saudeviz_ouro.fato_internacao_mensal
# MAGIC  GROUP BY complexidade, carater_internacao
# MAGIC HAVING SUM(internacoes) >= 1000
# MAGIC  ORDER BY permanencia_media DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Bloco 4 — Capacidade hospitalar
# MAGIC
# MAGIC *"Onde a capacidade está sendo ultrapassada?"*

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q9. Como a ocupação se distribui?
# MAGIC
# MAGIC ⚠️ **Cuidado metodológico:** a média simples entre municípios-mês é
# MAGIC enganosa — cidades minúsculas com 3 leitos pesam igual a São Paulo. A
# MAGIC consulta mostra a **média ponderada** por leitos-dia, que é a taxa real do
# MAGIC sistema, ao lado da média simples para deixar a distorção visível.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT porte,
# MAGIC        COUNT(DISTINCT cod_municipio_6)                                     AS municipios,
# MAGIC        SUM(internacoes)                                  AS internacoes,
# MAGIC        ROUND(AVG(taxa_ocupacao), 3)                                        AS ocupacao_media_simples,
# MAGIC        ROUND(SUM(dias_permanencia) / SUM(leitos_dia_disponiveis), 3)       AS ocupacao_ponderada,
# MAGIC        ROUND(AVG(leitos_por_100mil_hab), 1)                                AS leitos_por_100mil,
# MAGIC        SUM(deficit_leitos_oms)                                             AS deficit_leitos_oms
# MAGIC   FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC  GROUP BY porte
# MAGIC  ORDER BY ocupacao_ponderada DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** o gradiente por porte é a desigualdade
# MAGIC estrutural que o projeto se propôs a medir. Metrópoles e municípios
# MAGIC grandes operam próximos do limite; municípios pequenos têm leito ocioso.
# MAGIC
# MAGIC Isso **não** significa excesso de leito no interior — significa que o
# MAGIC paciente do interior se desloca para o centro, o que a próxima consulta
# MAGIC demonstra com dado.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q10. Quais municípios ultrapassaram a capacidade?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT municipio,
# MAGIC        uf,
# MAGIC        competencia,
# MAGIC        populacao,
# MAGIC        internacoes,
# MAGIC        leitos_sus,
# MAGIC        taxa_ocupacao,
# MAGIC        permanencia_media,
# MAGIC        situacao
# MAGIC   FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC  WHERE situacao IN ('Critica', 'Atencao')
# MAGIC  ORDER BY taxa_ocupacao DESC
# MAGIC  LIMIT 25;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura honesta — e isto precisa ser dito na apresentação:** ocupação
# MAGIC acima de 1,0 é um **alerta para investigar**, não prova de colapso. Há
# MAGIC três explicações possíveis, e o painel não distingue entre elas sozinho:
# MAGIC
# MAGIC 1. sobrecarga real da rede;
# MAGIC 2. leito não atualizado no CNES, subestimando o denominador;
# MAGIC 3. município polo que atende toda uma região de saúde.
# MAGIC
# MAGIC O valor da ferramenta é apontar **onde olhar**, reduzindo 1.668 municípios
# MAGIC a uma lista de dezenas. A decisão continua humana.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q11. Déficit de leitos frente ao parâmetro da OMS

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH por_municipio AS (
# MAGIC     -- O indicador e mensal: cada municipio aparece em ate 12 linhas.
# MAGIC     -- Reduzir a uma linha por municipio ANTES de somar e obrigatorio,
# MAGIC     -- senao o mesmo leito seria contado doze vezes.
# MAGIC     SELECT cod_municipio_6,
# MAGIC            uf,
# MAGIC            MAX(populacao)          AS populacao,
# MAGIC            MAX(leitos_sus)         AS leitos_sus,
# MAGIC            MAX(meta_leitos_oms)    AS meta_leitos_oms,
# MAGIC            MAX(deficit_leitos_oms) AS deficit_leitos_oms
# MAGIC       FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC      GROUP BY cod_municipio_6, uf
# MAGIC )
# MAGIC SELECT uf,
# MAGIC        COUNT(*)                                              AS municipios_com_internacao,
# MAGIC        SUM(populacao)                                        AS populacao_coberta,
# MAGIC        SUM(leitos_sus)                                       AS leitos_sus,
# MAGIC        ROUND(100000.0 * SUM(leitos_sus) / SUM(populacao), 1) AS leitos_por_100mil,
# MAGIC        300                                                   AS meta_oms_por_100mil,
# MAGIC        SUM(meta_leitos_oms)                                  AS meta_leitos,
# MAGIC        SUM(deficit_leitos_oms)                               AS deficit_leitos
# MAGIC   FROM por_municipio
# MAGIC  GROUP BY uf
# MAGIC  ORDER BY leitos_por_100mil ASC;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** os quatro estados do Sudeste operam abaixo do
# MAGIC parâmetro da OMS de 300 leitos por 100 mil habitantes. São Paulo, o mais
# MAGIC rico da federação, é também o mais distante da meta.
# MAGIC
# MAGIC ⚠️ **O déficit está subestimado de propósito.** Só entram municípios que
# MAGIC registraram internação em 2024 — 823 dos 1.668 do Sudeste. Municípios sem
# MAGIC nenhuma internação registrada não aparecem, e são justamente os que
# MAGIC dependem inteiramente da rede vizinha.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Bloco 5 — Padrões e agrupamentos
# MAGIC
# MAGIC *"Identificar semelhanças entre hospitais ou regiões. Separar perfis
# MAGIC críticos dos estáveis."*

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q12. Quem exporta paciente?
# MAGIC
# MAGIC **O diferencial da nossa análise.** A taxa de transferência responde à
# MAGIC pergunta de capacidade de um ângulo que o volume não alcança: não é
# MAGIC *"há muitas internações aqui"*, é ***"pacientes estão saindo daqui porque
# MAGIC não há como tratá-los aqui"***.
# MAGIC
# MAGIC Esse dado veio da coluna `COBRANCA` do SIH, que estava fora do nosso
# MAGIC recorte inicial de colunas. Foi incluída após validação empírica: os
# MAGIC códigos 41–43 somaram exatamente o mesmo total da coluna `MORTE`,
# MAGIC confirmando o mapeamento dos desfechos.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT municipio,
# MAGIC        uf,
# MAGIC        porte,
# MAGIC        SUM(internacoes)                          AS internacoes,
# MAGIC        SUM(transferencias)                                         AS transferencias,
# MAGIC        ROUND(100.0 * SUM(transferencias) / SUM(internacoes), 2)    AS taxa_transferencia,
# MAGIC        MAX(leitos_sus)                                             AS leitos_sus,
# MAGIC        ROUND(AVG(taxa_ocupacao), 3)                                AS ocupacao_media
# MAGIC   FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC  GROUP BY municipio, uf, porte
# MAGIC HAVING SUM(internacoes) >= 1000
# MAGIC  ORDER BY taxa_transferencia DESC
# MAGIC  LIMIT 20;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q13. Hospitais que retêm × hospitais que encaminham

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT nome_fantasia,
# MAGIC        uf,
# MAGIC        esfera,
# MAGIC        internacoes,
# MAGIC        leitos_sus,
# MAGIC        taxa_transferencia,
# MAGIC        permanencia_media,
# MAGIC        CASE WHEN taxa_transferencia >= 5 THEN 'Encaminha muito'
# MAGIC             WHEN taxa_transferencia >= 2 THEN 'Encaminha na media'
# MAGIC             ELSE 'Resolve internamente'
# MAGIC        END                            AS perfil_resolutividade
# MAGIC   FROM workspace.saudeviz_ouro.rank_hospitais
# MAGIC  WHERE internacoes >= 5000
# MAGIC  ORDER BY taxa_transferencia DESC
# MAGIC  LIMIT 25;

# COMMAND ----------

# MAGIC %md
# MAGIC **Leitura para a gestão:** dois hospitais de porte parecido com taxas de
# MAGIC transferência muito diferentes indicam **resolutividade** diferente. Para
# MAGIC a secretaria, isso orienta onde investir em complexidade instalada em vez
# MAGIC de simplesmente abrir mais leitos.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q14. Outliers de ocupação — critério de Tukey
# MAGIC
# MAGIC **Técnica estatística:** detecção por intervalo interquartil
# MAGIC (Q3 + 1,5 × IQR). Aqui o outlier superior **não é ruído a descartar** —
# MAGIC é exatamente o município que a gestão precisa enxergar.

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH quartis AS (
# MAGIC     SELECT PERCENTILE(taxa_ocupacao, 0.25) AS q1,
# MAGIC            PERCENTILE(taxa_ocupacao, 0.50) AS mediana,
# MAGIC            PERCENTILE(taxa_ocupacao, 0.75) AS q3
# MAGIC       FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC      WHERE taxa_ocupacao IS NOT NULL
# MAGIC ), limites AS (
# MAGIC     SELECT q1, mediana, q3,
# MAGIC            q3 - q1                    AS iqr,
# MAGIC            q3 + 1.5 * (q3 - q1)       AS limite_superior
# MAGIC       FROM quartis
# MAGIC )
# MAGIC SELECT ROUND(l.q1, 3)                                              AS q1,
# MAGIC        ROUND(l.mediana, 3)                                         AS mediana,
# MAGIC        ROUND(l.q3, 3)                                              AS q3,
# MAGIC        ROUND(l.iqr, 3)                                             AS iqr,
# MAGIC        ROUND(l.limite_superior, 3)                                 AS limite_outlier,
# MAGIC        COUNT(*)                                                    AS municipios_mes_outliers,
# MAGIC        ROUND(100.0 * COUNT(*)
# MAGIC              / (SELECT COUNT(*) FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC                  WHERE taxa_ocupacao IS NOT NULL), 2)              AS pct_do_total
# MAGIC   FROM workspace.saudeviz_ouro.ind_capacidade_municipal c
# MAGIC  CROSS JOIN limites l
# MAGIC  WHERE c.taxa_ocupacao > l.limite_superior
# MAGIC  GROUP BY l.q1, l.mediana, l.q3, l.iqr, l.limite_superior;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Q15. Correlação entre os indicadores
# MAGIC
# MAGIC **Técnica estatística:** correlação de Pearson. Responde à frente de
# MAGIC *explicabilidade* do desafio — quais fatores aparecem associados ao
# MAGIC aumento da pressão assistencial?

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT ROUND(CORR(taxa_ocupacao, permanencia_media), 3)         AS ocupacao_x_permanencia,
# MAGIC        ROUND(CORR(taxa_ocupacao, internacoes_por_10mil_hab), 3) AS ocupacao_x_internacoes_hab,
# MAGIC        ROUND(CORR(taxa_ocupacao, leitos_por_100mil_hab), 3)     AS ocupacao_x_leitos_hab,
# MAGIC        ROUND(CORR(taxa_ocupacao, taxa_transferencia), 3)        AS ocupacao_x_transferencia,
# MAGIC        ROUND(CORR(taxa_ocupacao, taxa_mortalidade), 3)          AS ocupacao_x_mortalidade,
# MAGIC        ROUND(CORR(permanencia_media, custo_medio_aih), 3)       AS permanencia_x_custo
# MAGIC   FROM workspace.saudeviz_ouro.ind_capacidade_municipal
# MAGIC  WHERE taxa_ocupacao IS NOT NULL;

# COMMAND ----------

# MAGIC %md
# MAGIC **Como ler correlação sem cair na armadilha:** correlação **não é causa**.
# MAGIC Uma associação forte entre permanência e custo é quase tautológica —
# MAGIC diária custa dinheiro. Já uma correlação **negativa** entre leitos por
# MAGIC habitante e ocupação é informativa: mostra que onde há menos estrutura, a
# MAGIC pressão é maior — o argumento central do projeto, agora quantificado.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Resumo executivo
# MAGIC
# MAGIC Consulta única que reúne os indicadores para o slide de abertura do pitch.

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT SUM(internacoes)                              AS internacoes_2024,
# MAGIC        SUM(valor_total) / 1e9                        AS bilhoes_reais,
# MAGIC        ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)              AS permanencia_media,
# MAGIC        ROUND(100.0 * SUM(obitos)         / SUM(internacoes), 2)        AS taxa_mortalidade,
# MAGIC        ROUND(100.0 * SUM(transferencias) / SUM(internacoes), 2)        AS taxa_transferencia,
# MAGIC        SUM(dias_permanencia)                         AS leitos_dia_consumidos
# MAGIC   FROM workspace.saudeviz_ouro.fato_internacao_mensal;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quais prints levar para o PPT
# MAGIC
# MAGIC | Consulta | Serve para | Entrega |
# MAGIC |---|---|---|
# MAGIC | **Q1 + Q2** | Prova de que as 3 fontes foram integradas | 2ª e 3ª |
# MAGIC | **Q3** | Sazonalidade e o cuidado com dias do mês | 4ª |
# MAGIC | **Q5** | "Onde as internações estão crescendo" | 5ª |
# MAGIC | **Q7** | Pressão relativa — o achado de saúde mental | 5ª |
# MAGIC | **Q9** | Gradiente de ocupação por porte | 5ª |
# MAGIC | **Q10** | Municípios críticos | 5ª |
# MAGIC | **Q12/Q13** | Transferências — o diferencial do projeto | 5ª |
# MAGIC | **Q14/Q15** | Técnicas estatísticas: IQR e Pearson | 4ª |
# MAGIC | **Resumo** | Números de abertura do pitch | 8ª |
# MAGIC
# MAGIC **Dica de captura:** no Databricks, cada resultado tem o botão `+` ao lado
# MAGIC de "Table" para gerar gráfico. Barras para Q4, Q7 e Q9; linha para Q3.
# MAGIC Gráfico rende print melhor que tabela para a apresentação — mas leve a
# MAGIC **tabela junto**, porque é ela que mostra o SQL que gerou o número.
