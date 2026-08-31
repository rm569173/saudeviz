# Estrutura do PPT — Sprint 2

**Arquivo a entregar:** `EC_Sprint_2_1TSCO_EvidenciasConstrucao_SaudeViz_Lucas_Colen.pptx`

Ordem das oito entregas exigidas pelo template. O texto de cada slide está
pronto — resta inserir as imagens de `apresentação/` e ajustar o visual.

**Convenção:** 🖼️ indica o print que entra no slide.

---

## Abertura

### Slide 1 — Capa
```
SaúdeViz
Painel inteligente de acesso hospitalar e perfil de atendimento

Challenge FIAP × Oracle 2026 · Sprint 2
Turma 1TSCOA
Lucas Ventura Araujo Ribas Colen — RM 569173
```

### Slide 2 — Identificação do grupo
Reaproveitar o slide 1 da Sprint 1.

### Slide 3 — Os números da entrega
```
5.546.817     internações do SIH/SUS ocorridas em 2024
R$ 10,03 bi   pagos pelo SUS no período
4 estados     ES, MG, RJ e SP — 89 milhões de habitantes
3.131         estabelecimentos com leito
9             tabelas na camada Gold do Oracle
```
🖼️ `eda_resumo_executivo.png`

---

## 1ª entrega — Sprint 1 atualizada

### Slide 4 — O que mudou desde a Sprint 1
| Prometido na Sprint 1 | Situação |
|---|---|
| 3 fontes: SQL, JSON e CSV | ✅ Entregue |
| Medallion Bronze → Prata → Ouro | ✅ Entregue, em PySpark no Databricks |
| Oracle Database como camada Gold | ✅ Entregue, 11 tabelas `T_SAUDE_*` |
| Análise preditiva | ✅ Entregue |
| Oracle Select AI | ⚠️ Indisponível na instância da FIAP — mecanismo equivalente implementado |
| External Table do CSV | ⚠️ Sem privilégio na conta acadêmica — DDL entregue |
| Power BI | 🔄 Substituído por Streamlit |
| Cobertura nacional | 🔄 Recorte no Sudeste para o MVP |

### Slide 5 — Quadro de gestão
🖼️ Print do Trello + link público do quadro

---

## 2ª entrega — MVP implementado e escopo entregue

### Slide 6 — O painel
🖼️ `painel_01_visao_geral.png`
```
Link: saudeviz.streamlit.app
Cinco páginas, conectado ao Oracle da FIAP em tempo real.
```

### Slide 7 — Onde a capacidade foi ultrapassada
🖼️ `painel_02_capacidade_status.png`
```
Folga 8.466 · Adequada 1.043 · Atenção 223 · Crítica 16
município-mês, em 823 municípios com internação registrada
```

### Slide 8 — Municípios sob pressão
🖼️ `painel_03_capacidade_criticos.png`

Ocupação acima de 1,0 é alerta para investigar, não prova de colapso: pode ser
sobrecarga real, leito desatualizado no CNES ou município-polo atendendo toda
uma região.

### Slide 9 — Quais perfis pressionam mais
🖼️ `painel_04_perfis_pressao.png`
```
Transtornos mentais: 1,9% das internações, 4,1% dos leitos-dia
Pressão relativa 2,15 · permanência 10,4 dias · custo médio R$ 521

Ocupa leito e não consome orçamento. Invisível num painel que só conta
atendimentos.
```

---

## 3ª entrega — Arquitetura final implementada

### Slide 10 — Desenho da arquitetura
🖼️ `arquitetura_solucao.png` — ocupar o slide inteiro, sem título por cima
(o diagrama já traz o seu).

Gerado por `docs/gera_diagrama.py`, com as mesmas cores do painel. Se algum
número mudar, rode o script de novo em vez de editar a imagem.

### Slide 11 — O que roda onde, e por quê
| Etapa | Onde | Motivo |
|---|---|---|
| Download e decode `.dbc` | Estação local | Formato proprietário do DATASUS, exige extensão C e FTP |
| Bronze, Prata, Ouro | Databricks | PySpark sobre tabelas Delta |
| Camada Gold | Oracle 19c FIAP | Camada de serviço consultada pelo painel |
| Painel e NL→SQL | Streamlit Cloud | Link público, código versionado |

### Slide 12 — Medallion materializada
🖼️ `databricks_catalog_medallion.png`

Não é diagrama: é o catálogo real com as três camadas.

### Slide 13 — A camada Gold no Oracle
🖼️ `oracle_contagem_tabelas.png` + `oracle_arvore_tabelas.png`

### Slide 14 — Integridade do modelo
🖼️ `pipeline_ouro_carga_oracle.png` e `oracle_integridade_totais.png`
```
Fato de internações      5.546.817
Indicador de capacidade  5.546.817
Ranking de hospitais     5.546.817

Três tabelas construídas por caminhos diferentes, mesmo total.
Nenhuma internação perdida ou duplicada.
```

### Slide 15 — O que não foi implementado, e por quê
| Item | Motivo | O que foi entregue |
|---|---|---|
| Oracle Select AI | Exige Autonomous Database. Verificado por consulta a `all_objects`: a instância 19c da FIAP não tem `DBMS_CLOUD_AI` | Tradutor NL→SQL próprio sobre os mesmos metadados + script de configuração pronto |
| External Table | Conta acadêmica sem `CREATE ANY DIRECTORY` | CSV carregado como tabela comum; DDL documentado |
| Cobertura nacional | Recorte no Sudeste para viabilizar o MVP | Pipeline parametrizado por UF |
| Clusterização K-Means | Cortada por prazo | Código de referência no repositório |

---

## 4ª entrega — Modelos analíticos e técnicas

### Slide 16 — As três fontes e seus formatos
🖼️ `extrai_sih_py_45.jpeg` · `extrai_cnes_py_152.jpg` · `extrai_ibge_py_73.jpg`
```
FONTE 1 — SIH/SUS (relacional)     ftp.retrbinary(...)   7.015.106 internações
FONTE 2 — CNES (JSON via API)      _get_json(...)        4.481 estabelecimentos
FONTE 3 — IBGE (CSV)               df.to_csv(...)        5.571 municípios
```

### Slide 17 — Tratamento do formato proprietário
🖼️ `extrai_sih_py_69.jpeg`

O `.dbc` do DATASUS é um DBF comprimido com PKWare DCL. A conversão roda em
diretório temporário com caminho ASCII, porque a extensão C não aceita
acentos no caminho.

### Slide 18 — A descoberta que reorientou o projeto
🖼️ `pipeline_prata_defasagem.png`
```
Defasagem entre internar e ser faturado:

0 meses   4.214.705   60,8%
1 mês     1.789.226   25,8%
2 meses     587.295    8,5%
3 meses     297.454    4,3%   ← acumulado: 99,4%

A competência do SIH é o mês de PAGAMENTO, não o da internação.
Corrigimos a dimensão temporal e ampliamos a ingestão até março/2025.
```

### Slide 19 — Análise exploratória
🖼️ `eda_q03_sazonalidade_grafico.png` · `eda_q07_pressao_grafico.png`

16 consultas SQL documentadas cobrindo as quatro frentes analíticas do desafio.

### Slide 20 — Técnicas estatísticas
🖼️ `eda_q14_outliers_iqr.png` · `eda_q15_correlacao.png`
```
Tukey (Q3 + 1,5×IQR): limite de outlier em 1,172

O critério estatístico, calculado sem referência ao nosso limiar, confirma
que ocupação acima de 1,0 é anômala nesta distribuição.

Pearson: ocupação × transferência = −0,305
Municípios com baixa ocupação transferem mais — não têm capacidade
resolutiva, estabilizam e encaminham.
```

### Slide 21 — Modelo de previsão
🖼️ `modelo_comparativo_horizonte.png`
```
horizonte   perfil semanal   regressão
     7d          6,32%          6,27%
    30d          5,77%          7,67%
    90d          5,46%         27,12%

Testamos regressão com tendência e sazonalidade. Perdeu em todos os
horizontes acima de 7 dias. A série não tem tendência explorável.
```

### Slide 22 — O que move a demanda
🖼️ `modelo_dia_semana.png` · `modelo_fator_feriado.png`
```
Sábado −38%  ·  Domingo −41%  ·  Feriado −26%

Consistente nos quatro estados. A queda do fim de semana é a rede eletiva
parada, não menos doentes.
```

---

## 5ª entrega — Evidências visuais

### Slide 23 — Previsão de demanda no painel
🖼️ `painel_05_previsao_serie.png`

### Slide 23b — Quantos leitos, e quando abrir
🖼️ `painel_07_dimensionamento.png`
```
Belo Horizonte  ·  6.312 leitos cadastrados

Demanda comum      5.107 leitos abertos o ano inteiro
Pico (abril)       5.904  →  +797 leitos sazonais
Folga no pico        408  →  6% da capacidade
```
A curva mensal diz ao gestor **quando** acionar capacidade extra e **qual é o
piso** que não pode ser desmobilizado. Abril é o pico nas quatro capitais.

Seis por cento de folga no pico é a margem que uma epidemia consome em dias.

### Slide 24 — Consultas na camada Gold
🖼️ `oracle_top10_hospitais.png`
```
Santa Casa BH        54.406 internações   0,21% transferência
HC-FMUSP SP          53.161               2,66%
Hosp. Base SJRP      50.043               1,09%
```

### Slide 25 — Onde as internações crescem
🖼️ `eda_q05_crescimento.png`

### Slide 26 — Quem exporta paciente
🖼️ `eda_q12_transferencias.png`
```
Embu-Guaçu/SP: 1.460 internações, 1.082 transferências, 15 leitos
74% dos pacientes seguem para outro município.
```

---

## Análise complementar — clima e internação

Não é entrega obrigatória. Responde ao critério de **inovação**: *"o quanto o
grupo foi além do esperado"*.

### Slide 26b — Uma quarta fonte
🖼️ `clima_01_fonte.png`
```
Open-Meteo · clima diário das 4 capitais · 2024

1.464 dias-capital · 526 com chuva
1.421.225 internações nas capitais

Três hipóteses testadas:
  chuva aumenta acidentes?
  frio aumenta doença respiratória?
  a estação do ano importa além do ciclo semanal?
```

### Slide 26c — Chuva não explica acidentes
🖼️ `clima_02_chuva_acidentes.png` · `clima_03_gradiente_chuva.png`
```
Com chuva   104,4 acidentes/dia
Sem chuva   105,1
variação     −0,7%

E sem gradiente por intensidade:
  Sem chuva      693 dias   105,4
  Chuva fraca    254        103,0
  Chuva moderada  85        110,4
  Chuva forte     16         83,1

Hipótese refutada.
```
O teste de gradiente é o que separa achado de coincidência. Se a chuva causasse
acidentes, o efeito cresceria com a intensidade. Sobe e desce sem padrão — e os
83,1 da chuva forte vêm de 16 dias apenas.

**Consequência prática:** o planejamento hospitalar não deve reservar
capacidade para dias de chuva. Não há efeito a antecipar.

### Slide 26d — Frio se associa a internação respiratória
🖼️ `clima_04_frio_respiratoria.png`
```
Muito frio   73,7 internações/dia
Quente       67,5
variação     +9,2%

Gradiente monotônico nas quatro capitais:

Capital           Muito frio   Frio   Ameno   Quente
Belo Horizonte          61,9   59,5    52,1     50,0
Rio de Janeiro          50,5   49,8    47,8     43,6
São Paulo              175,1  175,4   161,0    163,9
```
As faixas são quartis calculados dentro de cada capital: 18 °C é frio em
Vitória e ameno em São Paulo.

### Slide 26e — Só a temperatura mínima importa
🖼️ `clima_05_correlacao.png`
```
                temp_min   temp_max    chuva
Belo Horizonte    −0,306      0,020   −0,244
Rio de Janeiro    −0,185     −0,001   −0,129
Vitória           −0,148     −0,055   −0,181
São Paulo         −0,107      0,062   −0,139
```
A temperatura **máxima não tem correlação** — ronda zero nas quatro cidades.
É o frio da madrugada que se relaciona com internação respiratória, não o
calor do dia.

### Slide 26f — A ressalva que o próprio dado revela
```
A chuva aparece com correlação NEGATIVA: dias chuvosos têm menos internação
respiratória.

Contraintuitivo — até lembrar que no Sudeste chove no verão e a seca é no
inverno. A chuva está medindo a ESTAÇÃO, não a si mesma.

O mesmo confundimento pode valer para o frio: dias frios concentram-se no
inverno, que também tem mais circulação viral. Os 9,2% podem ser efeito da
temperatura, da sazonalidade viral, ou dos dois.

É associação, não causa.
```
Separar os dois efeitos exigiria dados de circulação viral por semana
epidemiológica — fora do escopo desta sprint, e registrado como próximo passo.

---

## Select AI

### Slide 27 — Perguntas em linguagem natural
🖼️ `painel_08_nlsql_exemplos.png`

### Slide 28 — O SQL gerado e executado
🖼️ `painel_09_nlsql_intencao.png` · `painel_10_nlsql_sql.png`
```
Duas perguntas, duas tabelas diferentes:

"quais hospitais mais transferem pacientes?"    → T_SAUDE_RANK_HOSPITAIS
"onde a capacidade esta sendo ultrapassada?"    → T_SAUDE_IND_CAPACIDADE_MUNICIPAL
```
A tabela é escolhida pela intenção reconhecida, não por uma consulta fixa.
```
O SQL continua sendo gerado e executado no Oracle. O tradutor remove a
barreira da sintaxe para quem decide.
```

### Slide 29 — Por que não é o Select AI nativo
🖼️ `oracle_comentarios_metadados.png`
```
SELECT COUNT(*) FROM all_objects
 WHERE object_name = 'DBMS_CLOUD_AI';   →  0

O Select AI existe apenas no Autonomous Database. Implementamos o mecanismo
equivalente sobre OS MESMOS metadados: os COMMENT ON das tabelas.

Migrar para o Autonomous não exige remodelar nada — só trocar o motor de
tradução. O script já está entregue.
```

---

## 6ª entrega — Repositório técnico

### Slide 30 — Código-fonte
🖼️ `github_repositorio.png`
```
github.com/rm569173/saudeviz

6 notebooks Databricks · pipeline de ingestão das 3 fontes
DDL do Oracle · tradutor NL→SQL · painel Streamlit
Camada Gold versionada para reprodução sem acesso ao banco
```

---

## 7ª entrega — Vídeo pitch

### Slide 31 — Link do vídeo
```
youtube.com/watch?v=________
Duração: até 5 minutos
```

---

## 8ª entrega — Resultados e conclusão

### Slide 32 — O que aprendemos com os dados
```
1. A competência do SIH não é a data da internação
   42% dos registros de um mês são de meses anteriores

2. A coluna COBRANCA revela transferência de paciente
   Muda "há muitas internações aqui" para "pacientes saem daqui porque
   não há como tratá-los aqui"

3. A demanda hospitalar não tem tendência explorável
   O sinal previsível está no ciclo semanal e nos feriados
```

### Slide 33 — Limitações declaradas
```
· Recorte no Sudeste — pipeline parametrizado por UF
· Dezembro/2024 com cobertura de 99,4%
· Ocupação acima de 1,0 é alerta, não diagnóstico
· Pacientes internados antes de 2024 não entram na contagem
  (medido: menos de 1% dos leitos-dia)
```

### Slide 34 — Próximos passos
```
· Separar o efeito do frio do efeito da sazonalidade viral, cruzando com
  dados de circulação respiratória por semana epidemiológica
· Estender ao Brasil inteiro — o pipeline já é parametrizado
· Migrar para o Autonomous Database e ativar o Select AI nativo
```

### Slide 35 — Encerramento
```
Dados que salvam vidas.
Decisões que transformam o sistema de saúde.

saudeviz.streamlit.app
github.com/rm569173/saudeviz
```

---

## Conferência antes de entregar

- [ ] Nome do arquivo no padrão exigido
- [ ] Link do painel funcionando, testado num navegador anônimo
- [ ] Link do GitHub público
- [ ] Link do vídeo no YouTube, não listado ou público
- [ ] Link do quadro Kanban público
- [ ] Nenhuma senha, token ou credencial visível em qualquer print
