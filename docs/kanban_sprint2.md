# Quadro Kanban — 1ª entrega da Sprint 2

**Quadro no Trello:** https://trello.com/b/3XTAInGQ

> ⚠️ **Pendente:** deixar o quadro **público** antes de entregar.
> Menu do quadro (⋯ no canto superior direito) → *Configurações* →
> *Visibilidade* → **Público**. Sem isso o avaliador não consegue abrir.
>
> ⚠️ **Pendente:** nomear as 6 etiquetas. Abra qualquer cartão → *Etiquetas* →
> lápis em cada cor:
> verde `Dados` · azul `Engenharia` · roxo `Análise` ·
> amarelo `Documentação` · laranja `Apresentação` · vermelho `Não implementado`

O quadro tem **44 cartões em 5 listas**, cada um com a evidência numérica na
descrição. O conteúdo abaixo é o rascunho que deu origem a ele — mantido como
registro, mas o Trello é a fonte atual.

---

## Lista: Sprint 1 ✅ — entregue em 16/06/2026

| Cartão | Etiqueta |
|---|---|
| Ideação e nome do projeto — SaúdeViz | Documentação |
| Contextualização do problema e análise de causas | Análise |
| Definição de público-alvo e proposta de solução | Documentação |
| Arquitetura inicial da solução | Engenharia |
| Definição da stack tecnológica | Engenharia |
| Protótipo 1 — dashboard executivo | Apresentação |
| Protótipo 2 — interface Select AI | Apresentação |
| Planejamento ágil e cronograma | Documentação |

---

## Lista: Sprint 2 — Concluído

| Cartão | Etiqueta | Evidência |
|---|---|---|
| Ingestão fonte 1 — SIH/SUS via FTP DATASUS | Dados | 7.015.106 registros, 60 arquivos `.dbc` |
| Ingestão fonte 2 — CNES via API REST JSON | Dados | 4.481 estabelecimentos |
| Ingestão fonte 2b — leitos hospitalares CNES | Dados | 18.644 registros |
| Ingestão fonte 3 — população municipal IBGE (CSV) | Dados | 5.571 municípios |
| **Descoberta: competência do SIH ≠ data de internação** | Análise | 42% de defasagem medida |
| Correção da dimensão temporal e reingestão até mar/2025 | Engenharia | cobertura de 99,4% |
| Validação empírica dos códigos de desfecho (`COBRANCA`) | Análise | 41–43 = total de `MORTE` |
| Provisionamento do Databricks e upload da landing zone | Engenharia | 218 MB, Unity Catalog |
| Camada Bronze em Delta | Engenharia | 4 tabelas |
| Camada Prata — limpeza, tipagem, decodificação | Engenharia | 6.934.245 registros |
| Camada Ouro — star schema | Engenharia | 6 tabelas |
| Teste de conectividade Databricks → Oracle | Engenharia | 6.401 linhas/s |
| Carga no Oracle 19c da FIAP | Engenharia | 6 tabelas conferidas |
| Notebook de EDA com 16 consultas SQL | Análise | 4 frentes do desafio |

---

## Lista: Sprint 2 — Em andamento

| Cartão | Etiqueta |
|---|---|
| Prints de evidência das consultas de EDA | Apresentação |
| Modelo de previsão de demanda hospitalar | Análise |

---

## Lista: Sprint 2 — A fazer

| Cartão | Etiqueta |
|---|---|
| Motor NL→SQL sobre os metadados das tabelas | Engenharia |
| Painel Streamlit | Engenharia |
| Deploy público no Streamlit Cloud | Engenharia |
| README e repositório GitHub público | Documentação |
| PPT com as 8 entregas da Sprint 2 | Apresentação |
| Planilha `Informacoes_Finais_Projeto_Integrantes` | Documentação |
| Roteiro e gravação do vídeo pitch (≤5 min) | Apresentação |
| Upload no YouTube e arquivo `.TXT` com o link | Apresentação |
| Empacotamento do `.zip` final | Documentação |

---

## Lista: Não implementado — com justificativa

Esta lista é a mais importante para a avaliação: mostra decisão consciente, não
esquecimento.

| Cartão | Motivo |
|---|---|
| **Oracle Select AI** | Exige Autonomous Database. A instância da FIAP é Oracle 19c Enterprise, sem `DBMS_CLOUD_AI` — verificado por consulta a `all_objects`. Script de configuração entregue em `src/db/ddl_oracle.sql` |
| **External Table do CSV** | Sem privilégio `CREATE ANY DIRECTORY` e sem diretórios visíveis. O CSV é carregado como tabela comum; DDL da External Table entregue documentado |
| **Power BI** | Substituído por Streamlit: gera link público real e mantém o código versionado no GitHub, que vale 20% da nota |
| **Clusterização K-Means** | Cortada por prazo após a decisão de migrar o pipeline para o Databricks. Código de referência existe em `src/analytics/clusterizacao.py` |
| **Cobertura nacional** | Recorte no Sudeste (ES, MG, RJ, SP — 89 milhões de habitantes) para viabilizar o MVP. O pipeline é parametrizado por UF em `src/config.py` |

---

## Observação sobre o método

O projeto foi conduzido em Scrum com quadro Kanban. Duas mudanças de rota
relevantes aconteceram durante a Sprint 2 e estão refletidas acima:

1. **Migração do pipeline para o Databricks**, decidida em 30/08 — o Medallion
   passou de pandas local para PySpark, com corte compensatório de escopo.
2. **Descoberta da defasagem de faturamento do SIH**, que obrigou a reingerir os
   dados com uma janela maior e a trocar a dimensão temporal de todo o modelo.

Ambas são exemplos de adaptação baseada em evidência — o que a metodologia ágil
prevê e o que uma entrega puramente verde no quadro esconderia.
