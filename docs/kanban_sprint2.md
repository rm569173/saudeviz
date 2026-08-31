# Quadro Kanban — Sprint 2

**Quadro público:** https://trello.com/b/3XTAInGQ

O quadro é a fonte da verdade: **44 cartões em 5 listas**, cada um com a
evidência numérica na descrição. Este arquivo não repete o conteúdo dele — duas
cópias mantidas à mão divergem, e a versão errada é sempre a que o avaliador
abre. Aqui fica só o que o quadro não consegue explicar.

## Como as listas estão organizadas

| Lista | Cartões | O que reúne |
|---|---|---|
| Sprint 1 ✅ | 8 | O que foi entregue em 16/06/2026 |
| Sprint 2 ✅ Concluído | 23 | Fontes, pipeline, Oracle, painel, análises |
| Sprint 2 🔄 Em andamento | 2 | PPT e este quadro |
| Sprint 2 📌 A fazer | 5 | Diagrama, planilha, vídeo, zip |
| ⛔ Não implementado | 5 | Com o motivo técnico de cada corte |

**Etiquetas:** 🟢 Dados · 🔵 Engenharia · 🟣 Análise · 🟡 Documentação ·
🟠 Apresentação · 🔴 Não implementado

## Por que a quinta lista existe

O template exige que *"as atividades que não foram concluídas devem constar
nesse planejamento no devido status em que se encontra"*.

Um quadro inteiramente verde esconderia as decisões de escopo, que são parte do
trabalho. A lista **Não implementado** registra cinco itens com o motivo
técnico e o que foi entregue no lugar:

| Item | Por quê |
|---|---|
| Oracle Select AI | Exige Autonomous. Verificado em `all_objects`: o 19c da FIAP não tem `DBMS_CLOUD_AI` |
| External Table | Conta acadêmica sem `CREATE ANY DIRECTORY` |
| Power BI | Trocado por Streamlit: link público real e código versionado |
| K-Means | Cortado por prazo após a migração para o Databricks |
| Cobertura nacional | Recorte no Sudeste para viabilizar o MVP |

## Duas mudanças de rota registradas no quadro

O projeto foi conduzido em Scrum com quadro Kanban. Duas decisões mudaram o
plano no meio da Sprint 2, e as duas estão refletidas nos cartões:

1. **Migração do pipeline para o Databricks**, decidida em 30/08/2026. O
   Medallion passou de pandas local para PySpark, com corte compensatório de
   escopo — a clusterização K-Means foi o que saiu.

2. **Descoberta da defasagem de faturamento do SIH**, que obrigou a reingerir os
   dados com uma janela maior e a trocar a dimensão temporal de todo o modelo, a
   três dias da entrega.

Ambas são adaptação baseada em evidência, que é o que a metodologia ágil prevê
e o que um quadro puramente verde esconderia.
