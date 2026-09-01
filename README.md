# SaúdeViz — Painel inteligente de acesso hospitalar e perfil de atendimento

**Challenge FIAP × Oracle 2026 · Turma 1TSCOA · Sprint 2**
Lucas Ventura Araujo Ribas Colen — RM 569173

Solução analítica que transforma microdados públicos de saúde em respostas que
um gestor consegue usar — sem depender de um analista SQL disponível o tempo
todo.

> **5.546.817 internações** do SIH/SUS ocorridas em 2024 na região Sudeste ·
> **R$ 10,0 bilhões** pagos · **3.131 estabelecimentos** com leito ·
> **1.668 municípios**

| | |
|---|---|
| 🖥️ **Painel no ar** | https://saudeviz.streamlit.app |
| 🎬 **Vídeo pitch** | https://youtu.be/3LEW0WdBYis |
| 📋 **Quadro Kanban** | https://trello.com/b/3XTAInGQ |
| 💾 **Repositório** | https://github.com/rm569173/saudeviz |

O painel consulta o **Oracle 19c da FIAP em tempo real**. A barra lateral
informa a origem do dado: se o banco não responder em 8 segundos, ele cai para
o retrato local e diz isso na tela — resultado de contingência nunca se passa
por dado ao vivo.

---

## O problema

Uma secretaria de saúde precisa responder três perguntas críticas, e hoje cada
uma delas exige abrir um chamado para a equipe técnica:

1. **Onde as internações estão crescendo?**
2. **Quais perfis de atendimento mais pressionam o sistema?**
3. **Onde a capacidade hospitalar está sendo ultrapassada?**

O SaúdeViz responde às três em segundos — e aceita a pergunta em português.

## Arquitetura

```
  FONTES                    PROCESSAMENTO              CONSUMO
  ──────                    ─────────────              ───────

  SIH/SUS  (.dbc)  ─┐
  FTP DATASUS       │
                    │      ┌─────────────┐      ┌──────────────┐
  CNES     (JSON)  ─┼─────►│  Databricks │─────►│  Oracle 19c  │
  API REST MS       │      │             │      │              │
                    │      │  Bronze     │      │  camada Gold │
  IBGE     (CSV)   ─┘      │  Prata      │      │  T_SAUDE_*   │
  API agregados            │  Ouro       │      └──────┬───────┘
                           └─────────────┘             │
                             PySpark + Delta           ▼
  Open-Meteo (JSON) ─ ─ ─ ─ ─ ─ ─┐               ┌──────────────┐
  clima diário                   │               │  Streamlit   │
                                 ▼               │              │
                          ┌─────────────┐        │  painel      │
                          │ 06_clima    │        │  NL→SQL      │
                          │ teste de    │        └──────────────┘
                          │ hipóteses   │
                          └─────────────┘
```

**Os três formatos exigidos pelo desafio, cada um com propósito:**

| Fonte | Formato | Por que este formato | Volume |
|---|---|---|---|
| SIH/SUS | Relacional | Agregações e filtros sobre 33 colunas de AIH | 7.015.106 registros |
| CNES | JSON via API | Atributos variam por estabelecimento — nem todo hospital preenche os mesmos campos | 4.481 estabelecimentos + 18.644 leitos |
| IBGE | CSV | Enriquecimento cadastral, lido diretamente | 5.571 municípios |

**E uma quarta fonte, que não era exigida:**

| Fonte | Formato | Para quê | Volume |
|---|---|---|---|
| Open-Meteo | JSON via API | Testar hipóteses que os dados de saúde sozinhos não respondem | 366 dias × 4 capitais |

A fonte de clima **não passa pelo Medallion**, e isso é deliberado: ela não faz
parte do modelo dimensional que o painel consulta. O notebook `06_clima` lê o
parquet direto da landing zone e faz uma análise fechada em si mesma. Empurrá-la
para Bronze/Prata/Ouro adicionaria três tabelas que nenhuma tela usa.

## O que descobrimos no caminho

Três achados que mudaram o projeto e estão documentados no código:

### 1. A competência do SIH não é a data da internação

`ANO_CMPT`/`MES_CMPT` é o mês em que a AIH foi **paga**, não em que o paciente
internou. Medido nos próprios dados:

| Defasagem entre internar e faturar | Participação |
|---|---|
| mesmo mês | 60,8% |
| 1 mês depois | 25,8% |
| 2 meses depois | 8,5% |
| 3 meses depois | 4,3% |

Usar a competência como eixo de tempo faria o painel responder uma pergunta
**financeira** enquanto promete uma **assistencial**. Corrigimos a dimensão
temporal para `dt_internacao` e ampliamos a ingestão até março/2025, para
recuperar as internações de dezembro faturadas com atraso.

### 2. A coluna que revela transferência estava fora do nosso recorte

O campo `COBRANCA` (motivo de saída da AIH) não estava nas 24 colunas
inicialmente selecionadas. Ao incluí-lo, validamos o mapeamento
empiricamente: os códigos 41–43 somaram **exatamente** o mesmo total da coluna
`MORTE`, confirmando o bloco de óbito.

Isso destravou a análise de **transferências** — que muda a frase do painel de
*"há muitas internações aqui"* para ***"pacientes estão saindo daqui porque não
há como tratá-los aqui"***.

### 3. A demanda hospitalar não tem tendência explorável

Testamos regressão com tendência, sazonalidade em Fourier e feriado. Ela
**perdeu** para um modelo de perfil semanal em todos os horizontes acima de
7 dias:

| Horizonte | Perfil semanal | Regressão |
|---|---|---|
| 7 dias | 6,32% | 6,27% |
| 30 dias | 5,77% | 7,67% |
| 90 dias | **5,46%** | 27,12% |

O sinal previsível está no **ciclo semanal** (sábado e domingo caem ~40%) e nos
**feriados** (−26%, com variação de apenas 3,5 pontos entre os quatro estados).
Reconhecer isso valeu mais que forçar complexidade sobre um fenômeno que não a
comporta.

### 4. Chuva não explica acidente; frio se associa a internação respiratória

Com a quarta fonte, duas hipóteses testadas e uma refutada:

| Hipótese | Resultado |
|---|---|
| Chuva aumenta internação por acidente | **Refutada.** −0,7%, e sem gradiente por intensidade da chuva |
| Frio aumenta internação respiratória | **Confirmada.** +9,2%, com gradiente monotônico nas quatro capitais |

O teste de gradiente é o que separa achado de coincidência: se a chuva causasse
acidentes, o efeito cresceria de chuva fraca para forte. Ele sobe e desce sem
padrão.

**A ressalva está declarada:** dias frios concentram-se no inverno, que também
tem mais circulação viral. Os 9,2% podem ser efeito da temperatura, da
sazonalidade, ou dos dois. É associação, não causa — separar exigiria dados de
circulação viral por semana epidemiológica.

Um resultado nulo bem medido vale tanto quanto um positivo: mostra que a
hipótese foi testada, e não escolhida depois de ver o dado.

## Sobre o Select AI

O **Select AI** da Oracle traduz linguagem natural em SQL usando os `COMMENT ON`
do dicionário de dados. Ele existe **apenas no Autonomous Database**.

A instância acadêmica da FIAP é um **Oracle 19c Enterprise** — verificamos por
consulta a `all_objects` que o pacote `DBMS_CLOUD_AI` não existe ali.

Implementamos então o mecanismo equivalente sobre **os mesmos metadados**: um
tradutor determinístico que classifica a intenção, extrai entidades (UF,
período, quantidade) e monta SQL a partir de modelos parametrizados. O SQL
gerado é real, executado e **exibido ao usuário** — o comportamento de
`SELECT AI showsql`.

O script de configuração do Select AI está entregue em
[`src/db/ddl_oracle.sql`](src/db/ddl_oracle.sql), pronto para rodar num
Autonomous. Migrar não exige remodelar nada — apenas trocar o motor de tradução.

## Estrutura do repositório

```
saudeviz/
├── app/                          Painel Streamlit
│   ├── streamlit_app.py          páginas e navegação
│   ├── dados.py                  acesso a dados (Oracle | parquet)
│   └── tema.py                   paleta validada para daltonismo
├── notebooks/                    Pipeline no Databricks
│   ├── 00_teste_conectividade_oracle.py
│   ├── 01_bronze.py              dado bruto em Delta
│   ├── 02_prata.py               limpeza, tipagem, decodificação
│   ├── 03_ouro.py                star schema + carga no Oracle
│   ├── 04_eda.py                 16 consultas SQL documentadas
│   ├── 05_previsao.py            modelo de previsão de demanda
│   └── 06_clima.py               teste de hipóteses clima × internação
├── src/
│   ├── config.py                 parâmetros do projeto
│   ├── ingestao/                 as quatro fontes
│   ├── medallion/                implementação de referência em pandas
│   ├── db/                       DDL Oracle, carga, Databricks
│   ├── analytics/                EDA e modelos (versão local)
│   └── selectai/                 tradutor NL→SQL e dicionário de dados
├── dados/ouro/                   camada Gold versionada (~6 MB)
├── apresentação/                 evidências: 53 prints + o diagrama
├── docs/                         roteiro do pitch, kanban, checklist
└── testar_conexao.py             diagnóstico do ambiente Oracle
```

## Como reproduzir

### 1. Ambiente

```bash
pip install -r requirements-dev.txt
```

### 2. Ingestão das fontes

```bash
py -m src.ingestao.extrai_sih      # SIH/SUS via FTP do DATASUS
py -m src.ingestao.extrai_leitos   # leitos do CNES
py -m src.ingestao.extrai_ibge     # população municipal (gera o CSV)
py -m src.medallion.prata          # necessário antes do CNES
py -m src.ingestao.extrai_cnes     # estabelecimentos via API REST
py -m src.ingestao.extrai_clima    # clima diário das capitais (Open-Meteo)
```

O `extrai_cnes` roda depois da Prata de propósito: ele busca só os CNES que
aparecem nas internações, em vez de varrer o cadastro inteiro.

O recorte (UFs e período) é parametrizado em
[`src/config.py`](src/config.py).

### 3. Pipeline no Databricks

Importe os notebooks de `notebooks/` no workspace e execute na ordem
`01` → `02` → `03`. Depois, em qualquer ordem: `04` (análise exploratória),
`05` (previsão) e `06` (clima). O `00` é só o teste de conectividade com o
Oracle, e vale rodar antes de tudo.

O envio dos arquivos para a landing zone:

```bash
py -m src.db.databricks_upload
```

### 4. Painel

```bash
streamlit run app/streamlit_app.py
```

Sem credenciais do Oracle, o painel roda em **modo contingência**: lê os
parquets de `dados/ouro/` e executa as consultas do tradutor via DuckDB. Todas
as funcionalidades continuam disponíveis; a interface informa a origem do dado.

Para conectar ao Oracle, copie `.streamlit/secrets.toml.exemplo` para
`.streamlit/secrets.toml` e preencha.

### 5. Documentos gerados por código

O diagrama de arquitetura, o PPTX de entrega e o teleprompter do pitch não
foram montados à mão:

```bash
py docs/gera_diagrama.py   # apresentação/arquitetura_solucao.png
py docs/gera_ppt.py        # o .pptx completo, 49 slides
py docs/mede_pitch.py      # cronometra o roteiro e gera o teleprompter
```

O motivo é o mesmo nos três: os números vêm do pipeline e mudam. Um slide
editado à mão vira número desatualizado em silêncio; um slide gerado é
reconstruído em segundos. O `mede_pitch` existe porque a primeira versão do
roteiro tinha 5min58s de fala num limite de 5 minutos — e ninguém percebeu,
porque o tempo estava estimado no olho em vez de contado.

## Segurança

Nenhuma credencial está versionada. `secrets.toml` está no `.gitignore`, as
senhas do Databricks ficam em *secret scope*, e o diagnóstico
`testar_conexao.py` pede a senha por prompt oculto sem gravá-la.

## Limitações declaradas

- **Recorte no Sudeste** (ES, MG, RJ, SP — 89 milhões de habitantes). O pipeline
  é parametrizado por UF.
- **Dezembro/2024 tem cobertura de ~99,4%** — internações faturadas a partir de
  abril/2025 não entraram na ingestão.
- **External Table não criada**: a conta acadêmica não tem
  `CREATE ANY DIRECTORY`. O CSV é carregado como tabela comum; o DDL da External
  Table está documentado no script.
- **Ocupação acima de 1,0 é alerta, não diagnóstico.** Pode indicar sobrecarga
  real, leito desatualizado no CNES ou município-polo que atende toda uma
  região de saúde.
- **Pacientes internados antes de 2024** que seguem hospitalizados não entram na
  contagem do ano — efeito medido em menos de 1% dos leitos-dia.

## Fontes de dados

| Fonte | Endereço |
|---|---|
| SIH/SUS | `ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados` |
| CNES — leitos | `ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/LT` |
| CNES — estabelecimentos | `apidadosabertos.saude.gov.br/cnes/estabelecimentos` |
| IBGE — população | `servicodados.ibge.gov.br/api/v3/agregados/6579` |

Todos os dados são públicos e de acesso livre.

---

*Desenvolvido para o Enterprise Challenge FIAP × Oracle, 2026.*
