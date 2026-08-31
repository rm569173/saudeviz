# Checklist de evidências visuais — 4ª e 5ª entregas

Organizado por **tela**, não por entrega: trocar de ambiente é o que consome
tempo. Capture tudo de uma tela antes de passar para a próxima.

**Salve tudo em** `apresentação/`, com os nomes indicados. O nome do arquivo
vira a legenda do slide.

⚠️ **Confira o tamanho de cada arquivo depois de salvar.** Dois prints com
exatamente o mesmo tamanho em bytes são o mesmo print salvo duas vezes — a
area de transferencia nao atualizou entre as capturas. Ja aconteceu uma vez
neste projeto.

**Como capturar no Windows:** `Win + Shift + S` → selecione a área → o print vai
para a área de transferência → cole no Paint e salve, ou use a notificação para
salvar direto.

---

## Antes de começar

- [ ] Reimportar `notebooks/04_eda.py` no Databricks — as consultas Q1 e Q11
      foram corrigidas depois da primeira execução
- [ ] Rodar o notebook inteiro e conferir que **Q3 e Q14 executam**
      (elas usam funções do Spark que não pude validar localmente)

---

## Tela 0 — Código de ingestão

Serve à **4ª entrega**, que pede explicitamente *"indicar todas as fontes de
dados utilizadas"* e *"entregar algoritmos, métodos, manipulações e
transformações"*.

| # | Arquivo | Trecho | Por que este trecho |
|---|---|---|---|
| A | `extrai_sih_py_45.jpeg` | `extrai_sih.py` linhas 45–67 | Conexão FTP e `retrbinary` — prova que o dado veio do servidor público |
| B | `extrai_sih_py_69.jpeg` | `extrai_sih.py` linhas 69–92 | ⭐ Conversão `.dbc` → `.dbf` → DataFrame. Formato proprietário do DATASUS que poucos conseguem abrir |
| C | `extrai_cnes_py_152.jpg` | `extrai_cnes.py` linhas 152–185 | GET no endpoint REST + o comentário sobre o filtro `uf=` que a API ignora em silêncio |
| D | `extrai_ibge_py_73.jpg` | `extrai_ibge.py` linhas 73–125 | Consumo da API e `to_csv` — prova que o CSV foi produzido pelo pipeline |

### E um slide-resumo com os três lado a lado

Além dos prints individuais, monte **um slide** com as três linhas essenciais.
Ele deixa óbvio num relance que os três formatos foram usados com propósito
diferente — que é exatamente o critério *"uso correto dos formatos"*:

```
FONTE 1 — SIH/SUS (relacional)
ftp.retrbinary(f"RETR {arq}", saida.write)     → 7.015.106 internações

FONTE 2 — CNES (JSON semiestruturado)
_get_json(f"{API_CNES}/{codigo}")              → 4.481 estabelecimentos

FONTE 3 — IBGE (CSV)
df.to_csv(CSV_POPULACAO, sep=";")              → 5.571 municípios
```

---

## Tela 1 — Databricks: notebook de EDA

Serve à **4ª entrega** (modelos e técnicas) e à **5ª** (evidências visuais).

> **Regra de ouro:** capture a **consulta SQL junto com o resultado**. O
> avaliador precisa ver que o número saiu de um SQL, não de um slide. É por isso
> que o print da célula inteira vale mais que o print só da tabela.

| # | Arquivo | O que enquadrar | Por que importa |
|---|---|---|---|
| 1 | `eda_q01_tres_fontes.png` | Q1 completa | Prova que as 3 fontes e os 3 formatos foram integrados |
| 2 | `eda_q02_integracao.png` | Q2 completa | 99,8% de integração entre SIH, CNES e IBGE |
| 3 | `eda_q03_sazonalidade.png` | Q3 + **gráfico de linha** | Mostra o cuidado com dias do mês |
| 4 | `eda_q05_crescimento.png` | Q5 completa | Responde "onde as internações crescem" |
| 5 | `eda_q07_pressao_perfil.png` | Q7 + **gráfico de barras** | ⭐ O achado de saúde mental |
| 6 | `eda_q09_ocupacao_porte.png` | Q9 + **gráfico de barras** | Gradiente de ocupação por porte |
| 7 | `eda_q10_municipios_criticos.png` | Q10 completa | Municípios acima da capacidade |
| 8 | `eda_q11_deficit_oms.png` | Q11 completa | Déficit de leitos por UF |
| 9 | `eda_q12_transferencias.png` | Q12 completa | ⭐ Embu-Guaçu com 74% de transferência |
| 10 | `eda_q14_outliers_iqr.png` | Q14 completa | Técnica estatística: Tukey |
| 11 | `eda_q15_correlacao.png` | Q15 completa | Técnica estatística: Pearson |
| 12 | `eda_resumo_executivo.png` | última consulta | Números de abertura do pitch |

**Para gerar gráfico:** no resultado, clique no **`+`** ao lado de "Table" →
escolha o tipo. Barras para Q7 e Q9; linha para Q3.

---

## Tela 2 — Databricks: pipeline

Serve à **2ª entrega** (MVP implementado) e à **3ª** (arquitetura).

| # | Arquivo | Onde | O que mostra |
|---|---|---|---|
| 13 | `pipeline_bronze_resumo.png` | `01_bronze`, célula final | Contagem das 4 tabelas Bronze |
| 14 | `pipeline_prata_defasagem.png` | `02_prata`, validação | ⭐ A tabela de defasagem de faturamento |
| 15 | `pipeline_ouro_situacao.png` | `03_ouro`, célula 4 | Distribuição Folga/Atenção/Crítica |
| 16 | `pipeline_ouro_ranking.png` | `03_ouro`, célula 5 | Top 10 hospitais |
| 17 | `pipeline_carga_oracle.png` | `03_ouro`, célula 9 | ⭐ Conferência Oracle × Databricks, tudo "sim" |
| 18 | `catalog_databricks.png` | menu **Catalog** | Os 3 schemas `saudeviz_*` com as tabelas |

---

## Tela 3 — Databricks: modelo de previsão

Serve à **4ª entrega**.

| # | Arquivo | Onde | O que mostra |
|---|---|---|---|
| 19 | `modelo_dia_semana.png` | `05_previsao`, célula 2 | Queda de ~40% no fim de semana |
| 20 | `modelo_fator_feriado.png` | `05_previsao`, célula 3 | Feriado reduz 26%, consistente nas 4 UFs |
| 21 | `modelo_coeficientes.png` | `05_previsao`, célula 4 | Efeito percentual por dia da semana |
| 22 | `modelo_comparativo_horizonte.png` | `05_previsao`, célula 6 | ⭐ Regressão degrada de 6% para 27% |

---

## Tela 4 — Oracle SQL Developer

Serve à **3ª entrega** (arquitetura) e à **6ª** (entregável técnico). **Esta é a
prova de que a camada Gold está no Oracle**, e não só num parquet.

| # | Arquivo | O que rodar |
|---|---|---|
| 23 | `oracle_tabelas.png` | `SELECT table_name, num_rows FROM user_tables WHERE table_name LIKE 'T_SAUDE%' ORDER BY 1;` |
| 24 | `oracle_comentarios.png` | `SELECT table_name, comments FROM user_tab_comments WHERE table_name LIKE 'T_SAUDE%';` |
| 25 | `oracle_consulta_negocio.png` | Uma consulta de negócio real, ex. o Top 10 de hospitais |

O print 24 é mais importante do que parece: são esses `COMMENT ON` que
alimentam o tradutor NL→SQL, e mostrá-los conecta o modelo de dados ao Select AI.

---

## Tela 5 — Painel Streamlit

Serve à **2ª entrega** (MVP) e à **5ª** (evidências). ⭐ São os prints mais
importantes do PPT.

| # | Arquivo | Página | Enquadrar | Feito |
|---|---|---|---|---|
| 26 | `painel_01_visao_geral.png` | Visão geral | Cartões + os dois gráficos | ✅ |
| 27 | `painel_02_capacidade_status.png` | Capacidade hospitalar | Cartões de status + gráfico de porte | ✅ |
| 28 | `painel_03_capacidade_criticos.png` | Capacidade, rolado | Tabela de municípios críticos | ✅ |
| 29 | `painel_04_perfis_pressao.png` | Perfis de atendimento | ⭐ Gráfico de pressão relativa | ✅ |
| 30 | `painel_05_previsao_serie.png` | Previsão de demanda | Série com intervalo de confiança | ✅ |
| 31 | `painel_06_previsao_modelos.png` | Previsão, rolado | Comparativo de modelos + efeito do dia da semana | ✅ |
| 32 | `painel_07_dimensionamento.png` | Previsão, fim da página | ⭐ Belo Horizonte — folga de 408 leitos (6%), alerta amarelo | ✅ |
| 33 | `painel_08_nlsql_exemplos.png` | Pergunte em português | Caixa de pergunta + os 8 exemplos | ✅ |
| 34 | `painel_09_nlsql_intencao.png` | Pergunte — "quais hospitais mais transferem pacientes?" | ⭐ Intenção 80% + SQL sobre `T_SAUDE_RANK_HOSPITAIS` + resultado | ✅ |
| 35 | `painel_10_nlsql_sql.png` | Pergunte — "onde a capacidade está sendo ultrapassada?" | ⭐ Intenção 75% + SQL sobre `T_SAUDE_IND_CAPACIDADE_MUNICIPAL` + "10 linhas retornadas do Oracle Database" | ✅ |
| 36 | `painel_12_sidebar_oracle.png` | qualquer | Barra lateral mostrando o modo de conexão | ✅ |

Os prints 34 e 35 são **duas perguntas diferentes**, cada uma completa da
pergunta ao resultado. Provam que o tradutor escolhe a tabela pela intenção —
mais forte do que fatiar uma única consulta em três imagens.

**O print 32 usa Belo Horizonte** de propósito: é a capital com a menor folga
no pico e a única em que o painel dispara o alerta amarelo. Uma capital folgada
mostraria a mesma tela sem mostrar que ela avalia.

**Dica:** capture com a barra lateral visível. Ela mostra o nome do projeto, seu
RM e o modo de conexão — contexto de graça em cada print.

---

## Tela 7 — Databricks: clima e internação

Serve ao critério de **inovação** e reforça a **4ª entrega**. É a única parte
do projeto que usa uma fonte além das três exigidas.

| # | Arquivo | Seção do `06_clima` | O que mostra |
|---|---|---|---|
| 39 | `clima_01_fonte.png` | 1 | As 4 capitais, temperaturas e chuva do ano |
| 40 | `clima_02_chuva_acidentes.png` | 4 | Acidentes em dias com e sem chuva |
| 41 | `clima_03_gradiente_chuva.png` | 5 | ⭐ Efeito por intensidade da chuva |
| 42 | `clima_04_frio_respiratoria.png` | 6 | Respiratórias por faixa de temperatura |
| 43 | `clima_05_correlacao.png` | 7 | Correlação temperatura × internação |
| 44 | `clima_06_onda_frio.png` | 8 | Efeito de dois dias seguidos de frio |
| 45 | `clima_07_estacao_perfil.png` | 9 | Índice sazonal por perfil de atendimento |
| 46 | `clima_08_resumo_hipoteses.png` | 10 | ⭐ Variação percentual de cada hipótese |

⚠️ **Capture mesmo que a hipótese seja refutada.** Um resultado nulo bem medido
vale mais que um achado forçado — e mostra que você testou de verdade em vez de
partir da conclusão. O slide muda de *"a chuva aumenta acidentes em X%"* para
*"testamos e a chuva não explica os acidentes; o planejamento não deve contar
com isso"*.

O print 41 é o mais importante: se existe efeito real, ele cresce com a
intensidade da chuva. Diferença sem gradiente é provavelmente ruído.

---

## Tela 6 — GitHub

Serve à **6ª entrega**.

| # | Arquivo | O que mostra |
|---|---|---|
| 37 | `github_repositorio.png` | Página inicial com o README renderizado |
| 38 | `github_estrutura.png` | Árvore de pastas expandida |

---

## Conferência final

- [ ] 55 arquivos em `apresentação/`
- [ ] Nenhum par de arquivos com o mesmo tamanho em bytes
- [ ] Nenhum print com senha, token ou dado pessoal visível
- [ ] Nenhum print com notificação do Windows aparecendo
- [ ] Todos legíveis quando reduzidos ao tamanho de um slide

⚠️ **Antes de capturar qualquer tela do Databricks ou do SQL Developer:** confira
que nenhuma célula de saída mostra credencial. O notebook de conectividade
imprime só o comprimento do token, mas vale conferir.
