# SaúdeViz — Painel inteligente de acesso hospitalar e perfil de atendimento

**Challenge FIAP × Oracle 2026 · Turma 1TSCOA · Sprint 2**
Lucas Ventura Araujo Ribas Colen — RM 569173

Solução analítica que transforma microdados públicos de saúde em respostas que
um gestor consegue usar — sem depender de um analista SQL disponível o tempo
todo.

> **5.546.817 internações** do SIH/SUS ocorridas em 2024 na região Sudeste ·
> **R$ 10,0 bilhões** pagos · **3.131 estabelecimentos** com leito ·
> **1.668 municípios**

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
                                                ┌──────────────┐
                                                │  Streamlit   │
                                                │              │
                                                │  painel      │
                                                │  NL→SQL      │
                                                └──────────────┘
```

**Os três formatos exigidos pelo desafio, cada um com propósito:**

| Fonte | Formato | Por que este formato | Volume |
|---|---|---|---|
| SIH/SUS | Relacional | Agregações e filtros sobre 33 colunas de AIH | 7.015.106 registros |
| CNES | JSON via API | Atributos variam por estabelecimento — nem todo hospital preenche os mesmos campos | 4.481 estabelecimentos |
| IBGE | CSV | Enriquecimento cadastral, lido diretamente | 5.571 municípios |

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
│   └── 05_previsao.py            modelos preditivo e explicativo
├── src/
│   ├── config.py                 parâmetros do projeto
│   ├── ingestao/                 as três fontes
│   ├── medallion/                implementação de referência em pandas
│   ├── db/                       DDL Oracle, carga, Databricks
│   ├── analytics/                EDA e modelos (versão local)
│   └── selectai/                 tradutor NL→SQL e dicionário de dados
├── dados/ouro/                   camada Gold versionada (~6 MB)
├── docs/                         documentação de apoio
└── testar_conexao.py             diagnóstico do ambiente Oracle
```

## Como reproduzir

### 1. Ambiente

```bash
pip install -r requirements-dev.txt
```

### 2. Ingestão das três fontes

```bash
py -m src.ingestao.extrai_sih      # SIH/SUS via FTP do DATASUS
py -m src.ingestao.extrai_leitos   # leitos do CNES
py -m src.ingestao.extrai_ibge     # população municipal (gera o CSV)
py -m src.medallion.prata          # necessário antes do CNES
py -m src.ingestao.extrai_cnes     # estabelecimentos via API REST
```

O recorte (UFs e período) é parametrizado em
[`src/config.py`](src/config.py).

### 3. Pipeline no Databricks

Importe os notebooks de `notebooks/` no workspace e execute na ordem
`01` → `02` → `03` → `05`. O envio dos arquivos para a landing zone:

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
