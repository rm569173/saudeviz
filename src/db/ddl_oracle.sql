-- ===========================================================================
-- SaudeViz - DDL da camada Gold no Oracle Database
-- Challenge FIAP x Oracle 2026 - 1TSCOA
-- Lucas Ventura Araujo Ribas Colen - RM 569173
--
-- Ordem de execucao:
--   1) tabelas dimensionais e fato (secao 1)
--   2) EXTERNAL TABLE do CSV de populacao (secao 2)
--   3) indices (secao 3)
--   4) views de negocio (secao 4)
--   5) configuracao do Select AI (secao 5)
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. MODELO DIMENSIONAL (star schema)
-- ---------------------------------------------------------------------------

DROP TABLE t_saude_fato_internacao CASCADE CONSTRAINTS;
DROP TABLE t_saude_ind_capacidade  CASCADE CONSTRAINTS;
DROP TABLE t_saude_rank_hospitais  CASCADE CONSTRAINTS;
DROP TABLE t_saude_serie_uf        CASCADE CONSTRAINTS;
DROP TABLE t_saude_previsao        CASCADE CONSTRAINTS;
DROP TABLE t_saude_cluster_municipio CASCADE CONSTRAINTS;
DROP TABLE t_saude_dim_estabelecimento CASCADE CONSTRAINTS;
DROP TABLE t_saude_dim_municipio   CASCADE CONSTRAINTS;

-- Fonte 3 (CSV / IBGE): dimensao de municipios
CREATE TABLE t_saude_dim_municipio (
    cod_municipio_6   VARCHAR2(6)   NOT NULL,
    cod_municipio     VARCHAR2(7),
    municipio         VARCHAR2(120),
    uf                VARCHAR2(2),
    uf_nome           VARCHAR2(60),
    regiao            VARCHAR2(20),
    populacao         NUMBER(10),
    porte             VARCHAR2(20),
    meta_leitos_oms   NUMBER(10),
    CONSTRAINT pk_saude_dim_municipio PRIMARY KEY (cod_municipio_6)
);

COMMENT ON TABLE  t_saude_dim_municipio IS
    'Municipios brasileiros com populacao estimada IBGE 2024, regiao, porte e meta de leitos pelo parametro OMS de 300 leitos por 100 mil habitantes.';
COMMENT ON COLUMN t_saude_dim_municipio.cod_municipio_6 IS
    'Codigo IBGE do municipio com 6 digitos, formato usado pelo SIH/SUS.';
COMMENT ON COLUMN t_saude_dim_municipio.meta_leitos_oms IS
    'Quantidade de leitos que o municipio deveria ter segundo o parametro OMS.';
COMMENT ON COLUMN t_saude_dim_municipio.porte IS
    'Classificacao por populacao: Pequeno I, Pequeno II, Medio, Grande, Metropole.';

-- Fonte 2 (JSON / API CNES + arquivos LT): dimensao de estabelecimentos
CREATE TABLE t_saude_dim_estabelecimento (
    cnes                       VARCHAR2(7)  NOT NULL,
    cod_municipio_6            VARCHAR2(6),
    uf                         VARCHAR2(2),
    nome_fantasia              VARCHAR2(200),
    esfera                     VARCHAR2(60),
    tipo_gestao                VARCHAR2(2),
    cod_tipo_unidade           NUMBER(5),
    tem_atendimento_hospitalar NUMBER(1),
    tem_centro_cirurgico       NUMBER(1),
    leitos_existentes          NUMBER(10),
    leitos_sus                 NUMBER(10),
    latitude                   NUMBER(12, 8),
    longitude                  NUMBER(12, 8),
    CONSTRAINT pk_saude_dim_estab PRIMARY KEY (cnes)
);

COMMENT ON TABLE  t_saude_dim_estabelecimento IS
    'Estabelecimentos de saude do CNES com leitos existentes e leitos disponibilizados ao SUS.';
COMMENT ON COLUMN t_saude_dim_estabelecimento.leitos_sus IS
    'Leitos que o estabelecimento disponibiliza ao SUS; denominador da taxa de ocupacao.';

-- Fonte 1 (SIH/SUS): fato agregado de internacoes
CREATE TABLE t_saude_fato_internacao (
    cod_municipio_6    VARCHAR2(6),
    uf                 VARCHAR2(2),
    ano                NUMBER(4),
    mes                NUMBER(2),
    competencia        VARCHAR2(6),
    perfil_atendimento VARCHAR2(80),
    complexidade       VARCHAR2(40),
    carater_internacao VARCHAR2(60),
    internacoes        NUMBER(12),
    dias_permanencia   NUMBER(14),
    permanencia_media  NUMBER(10, 2),
    diarias_uti        NUMBER(14),
    obitos             NUMBER(12),
    valor_total        NUMBER(16, 2),
    valor_medio_aih    NUMBER(14, 2),
    idade_media        NUMBER(6, 1),
    taxa_mortalidade   NUMBER(6, 2)
);

COMMENT ON TABLE t_saude_fato_internacao IS
    'Internacoes do SIH/SUS agregadas por municipio de atendimento, competencia mensal, perfil de atendimento (capitulo CID-10), complexidade e carater da internacao.';
COMMENT ON COLUMN t_saude_fato_internacao.perfil_atendimento IS
    'Capitulo CID-10 do diagnostico principal; responde "quais perfis pressionam o sistema".';
COMMENT ON COLUMN t_saude_fato_internacao.competencia IS
    'Competencia no formato AAAAMM.';

-- Indicador de pressao assistencial por municipio e mes
CREATE TABLE t_saude_ind_capacidade (
    cod_municipio_6          VARCHAR2(6),
    uf                       VARCHAR2(2),
    ano                      NUMBER(4),
    mes                      NUMBER(2),
    competencia              VARCHAR2(6),
    municipio                VARCHAR2(120),
    uf_nome                  VARCHAR2(60),
    regiao                   VARCHAR2(20),
    porte                    VARCHAR2(20),
    populacao                NUMBER(10),
    internacoes              NUMBER(12),
    dias_permanencia         NUMBER(14),
    diarias_uti              NUMBER(14),
    obitos                   NUMBER(12),
    valor_total              NUMBER(16, 2),
    leitos_existentes        NUMBER(10),
    leitos_sus               NUMBER(10),
    leitos_dia_disponiveis   NUMBER(14, 1),
    taxa_ocupacao            NUMBER(10, 3),
    internacoes_por_10mil_hab NUMBER(12, 3),
    leitos_por_100mil_hab    NUMBER(12, 3),
    meta_leitos_oms          NUMBER(10),
    deficit_leitos_oms       NUMBER(10),
    permanencia_media        NUMBER(10, 2),
    taxa_mortalidade         NUMBER(6, 2),
    custo_medio_aih          NUMBER(14, 2),
    situacao                 VARCHAR2(40)
);

COMMENT ON TABLE t_saude_ind_capacidade IS
    'Pressao assistencial por municipio e mes. taxa_ocupacao = dias de permanencia consumidos dividido por leitos SUS vezes 30,4 dias. Valores acima de 1 indicam demanda acima da capacidade instalada.';
COMMENT ON COLUMN t_saude_ind_capacidade.situacao IS
    'Classificacao da taxa de ocupacao: Folga (ate 0,70), Adequada (ate 0,85), Atencao (ate 1,00), Critica (acima de 1,00).';

-- Ranking de estabelecimentos
CREATE TABLE t_saude_rank_hospitais (
    cnes              VARCHAR2(7),
    uf                VARCHAR2(2),
    cod_municipio_6   VARCHAR2(6),
    nome_fantasia     VARCHAR2(200),
    esfera            VARCHAR2(60),
    internacoes       NUMBER(12),
    dias_permanencia  NUMBER(14),
    permanencia_media NUMBER(10, 2),
    diarias_uti       NUMBER(14),
    obitos            NUMBER(12),
    valor_total       NUMBER(16, 2),
    leitos_existentes NUMBER(10),
    leitos_sus        NUMBER(10),
    taxa_mortalidade  NUMBER(6, 2),
    custo_medio_aih   NUMBER(14, 2),
    giro_leito_ano    NUMBER(10, 1),
    ranking_nacional  NUMBER(10),
    latitude          NUMBER(12, 8),
    longitude         NUMBER(12, 8)
);

COMMENT ON TABLE t_saude_rank_hospitais IS
    'Ranking de estabelecimentos por volume de internacoes SUS, com permanencia media, mortalidade, custo medio por AIH e giro de leito.';

-- Serie temporal por UF (insumo do modelo de previsao)
CREATE TABLE t_saude_serie_uf (
    uf               VARCHAR2(2),
    ano              NUMBER(4),
    mes              NUMBER(2),
    competencia      VARCHAR2(6),
    internacoes      NUMBER(12),
    dias_permanencia NUMBER(14),
    valor_total      NUMBER(16, 2),
    obitos           NUMBER(12),
    data             DATE
);

COMMENT ON TABLE t_saude_serie_uf IS
    'Serie temporal mensal de internacoes por UF, usada no modelo de previsao de demanda.';

-- Saida do modelo preditivo
CREATE TABLE t_saude_previsao (
    uf                  VARCHAR2(2),
    data                DATE,
    competencia         VARCHAR2(6),
    internacoes_reais   NUMBER(12),
    internacoes_previstas NUMBER(12),
    limite_inferior     NUMBER(12),
    limite_superior     NUMBER(12),
    tipo                VARCHAR2(20),
    erro_percentual     NUMBER(10, 2)
);

COMMENT ON TABLE t_saude_previsao IS
    'Previsao de internacoes por UF gerada por regressao linear com componente sazonal mensal. tipo indica se a linha e historico ou previsao.';

-- Saida da clusterizacao
CREATE TABLE t_saude_cluster_municipio (
    cod_municipio_6     VARCHAR2(6),
    municipio           VARCHAR2(120),
    uf                  VARCHAR2(2),
    regiao              VARCHAR2(20),
    populacao           NUMBER(10),
    internacoes         NUMBER(12),
    taxa_ocupacao_media NUMBER(10, 3),
    permanencia_media   NUMBER(10, 2),
    leitos_por_100mil_hab NUMBER(12, 3),
    custo_medio_aih     NUMBER(14, 2),
    taxa_mortalidade    NUMBER(6, 2),
    cluster             NUMBER(3),
    perfil_cluster      VARCHAR2(60)
);

COMMENT ON TABLE t_saude_cluster_municipio IS
    'Agrupamento de municipios por similaridade de pressao assistencial (K-Means), com rotulo de negocio atribuido a cada cluster.';

-- ===========================================================================
-- 2. EXTERNAL TABLE - fonte 3 lida diretamente do CSV
--
--    *** ESTA SECAO NAO EXECUTA NO AMBIENTE DA FIAP ***
--
-- Verificado em 30/08/2026 contra oracle.fiap.com.br (Oracle 19c Enterprise,
-- usuario RM569173), com o script testar_conexao.py:
--
--   SELECT COUNT(*) FROM session_privs
--    WHERE privilege = 'CREATE ANY DIRECTORY';   ->  0
--   SELECT directory_name FROM all_directories;  ->  nenhuma linha
--
-- Sem um objeto DIRECTORY o Oracle nao tem como localizar o arquivo: a
-- EXTERNAL TABLE le do sistema de arquivos do SERVIDOR de banco, e nao da
-- maquina do cliente. O CSV precisaria estar dentro do host da faculdade,
-- ao qual o aluno nao tem acesso.
--
-- O que foi feito no MVP: o CSV do IBGE e carregado em
-- T_SAUDE_DIM_MUNICIPIO como tabela comum, pelo modulo src/db/carga.py.
-- A leitura continua sendo de um CSV - o que muda e o mecanismo de entrada.
--
-- O DDL abaixo fica entregue pronto para rodar num ambiente com o
-- privilegio concedido (Oracle Autonomous ou instancia propria), executando
-- antes, como DBA:
--   CREATE OR REPLACE DIRECTORY dir_saudeviz AS '/opt/oracle/saudeviz';
--   GRANT READ, WRITE ON DIRECTORY dir_saudeviz TO <usuario>;
-- e copiando dados/raw/populacao_municipios.csv para esse diretorio.
-- ===========================================================================

DROP TABLE t_saude_ext_populacao;

CREATE TABLE t_saude_ext_populacao (
    cod_municipio   VARCHAR2(7),
    municipio       VARCHAR2(120),
    uf              VARCHAR2(2),
    uf_nome         VARCHAR2(60),
    regiao          VARCHAR2(20),
    populacao       NUMBER(10),
    porte           VARCHAR2(20),
    ano_referencia  NUMBER(4),
    cod_municipio_6 VARCHAR2(6),
    meta_leitos_oms NUMBER(10)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY dir_saudeviz
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        CHARACTERSET AL32UTF8
        SKIP 1
        BADFILE     dir_saudeviz: 'populacao.bad'
        LOGFILE     dir_saudeviz: 'populacao.log'
        FIELDS TERMINATED BY ';'
        OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            cod_municipio, municipio, uf, uf_nome, regiao,
            populacao, porte, ano_referencia, cod_municipio_6, meta_leitos_oms
        )
    )
    LOCATION ('populacao_municipios.csv')
)
REJECT LIMIT UNLIMITED;

COMMENT ON TABLE t_saude_ext_populacao IS
    'Fonte 3 do challenge: CSV do IBGE com populacao municipal lido como External Table, sem carga previa no banco.';

-- ---------------------------------------------------------------------------
-- 3. INDICES
-- ---------------------------------------------------------------------------
CREATE INDEX ix_fato_competencia  ON t_saude_fato_internacao (competencia);
CREATE INDEX ix_fato_municipio    ON t_saude_fato_internacao (cod_municipio_6);
CREATE INDEX ix_fato_uf_perfil    ON t_saude_fato_internacao (uf, perfil_atendimento);
CREATE INDEX ix_capac_competencia ON t_saude_ind_capacidade (competencia);
CREATE INDEX ix_capac_situacao    ON t_saude_ind_capacidade (situacao);
CREATE INDEX ix_capac_uf          ON t_saude_ind_capacidade (uf);
CREATE INDEX ix_rank_uf           ON t_saude_rank_hospitais (uf);

-- ---------------------------------------------------------------------------
-- 4. VIEWS DE NEGOCIO
-- Nomes e comentarios em linguagem de negocio: sao esses metadados que o
-- Select AI usa para traduzir perguntas em portugues para SQL.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_saude_regioes_criticas AS
SELECT municipio,
       uf,
       regiao,
       competencia,
       populacao,
       internacoes,
       leitos_sus,
       taxa_ocupacao,
       deficit_leitos_oms,
       situacao
  FROM t_saude_ind_capacidade
 WHERE situacao = 'Critica'
 ORDER BY taxa_ocupacao DESC;

COMMENT ON TABLE v_saude_regioes_criticas IS
    'Municipios cuja demanda por internacao superou a capacidade de leitos SUS no mes.';

CREATE OR REPLACE VIEW v_saude_perfil_pressao AS
SELECT perfil_atendimento,
       uf,
       competencia,
       SUM(internacoes)      AS internacoes,
       SUM(dias_permanencia) AS dias_permanencia,
       ROUND(SUM(dias_permanencia) / NULLIF(SUM(internacoes), 0), 2) AS permanencia_media,
       SUM(valor_total)      AS valor_total
  FROM t_saude_fato_internacao
 GROUP BY perfil_atendimento, uf, competencia;

COMMENT ON TABLE v_saude_perfil_pressao IS
    'Quais perfis de atendimento (capitulos CID-10) mais pressionam o sistema por UF e mes.';

CREATE OR REPLACE VIEW v_saude_crescimento_municipio AS
SELECT cod_municipio_6,
       municipio,
       uf,
       competencia,
       internacoes,
       LAG(internacoes) OVER (PARTITION BY cod_municipio_6 ORDER BY competencia)
           AS internacoes_mes_anterior,
       ROUND(
           (internacoes
            - LAG(internacoes) OVER (PARTITION BY cod_municipio_6 ORDER BY competencia))
           / NULLIF(LAG(internacoes) OVER (PARTITION BY cod_municipio_6 ORDER BY competencia), 0)
           * 100, 2) AS variacao_percentual
  FROM t_saude_ind_capacidade;

COMMENT ON TABLE v_saude_crescimento_municipio IS
    'Variacao percentual de internacoes mes a mes por municipio; responde onde as internacoes estao crescendo.';

-- ===========================================================================
-- 5. SELECT AI - perguntas em linguagem natural
--
--    *** ESTA SECAO NAO EXECUTA NO AMBIENTE DA FIAP ***
--
-- Verificado em 30/08/2026 contra oracle.fiap.com.br com testar_conexao.py:
--
--   SELECT COUNT(*) FROM all_objects
--    WHERE object_name = 'DBMS_CLOUD_AI';        ->  0
--
-- O Select AI e um recurso do Oracle Autonomous Database. A instancia
-- academica da FIAP e um Oracle Database 19c Enterprise tradicional, onde o
-- pacote DBMS_CLOUD_AI nao existe.
--
-- O que foi feito no MVP: implementamos em src/selectai/ um tradutor de
-- linguagem natural para SQL que consome os MESMOS metadados que o Select AI
-- consumiria - os COMMENT ON TABLE e COMMENT ON COLUMN declarados neste
-- script. Por isso os comentarios acima estao escritos em linguagem de
-- negocio e nao em jargao tecnico: eles sao o contexto do tradutor.
--
-- Consequencia pratica: migrar para o Autonomous e executar a secao abaixo
-- nao exige reescrever o modelo de dados, apenas trocar o motor de traducao.
-- ===========================================================================

-- 5.1 Credencial do provedor de IA
BEGIN
    DBMS_CLOUD.CREATE_CREDENTIAL(
        credential_name => 'CRED_SAUDEVIZ_AI',
        username        => 'SAUDEVIZ',
        password        => '<API_KEY_DO_PROVEDOR>'
    );
END;
/

-- 5.2 Perfil do Select AI apontando para as tabelas da camada Gold
BEGIN
    DBMS_CLOUD_AI.CREATE_PROFILE(
        profile_name => 'PERFIL_SAUDEVIZ',
        attributes   => '{
            "provider":       "oci",
            "credential_name":"CRED_SAUDEVIZ_AI",
            "object_list": [
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_IND_CAPACIDADE"},
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_FATO_INTERNACAO"},
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_DIM_MUNICIPIO"},
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_DIM_ESTABELECIMENTO"},
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_RANK_HOSPITAIS"},
                {"owner": "SAUDEVIZ", "name": "T_SAUDE_SERIE_UF"}
            ],
            "comments": "true"
        }');
END;
/

-- 5.3 Ativar o perfil na sessao
BEGIN
    DBMS_CLOUD_AI.SET_PROFILE('PERFIL_SAUDEVIZ');
END;
/

-- 5.4 Exemplos de perguntas em linguagem natural
-- SELECT AI  quais municipios tiveram maior crescimento de internacoes no ultimo trimestre;
-- SELECT AI  quais perfis de atendimento mais pressionam o sistema no Nordeste;
-- SELECT AI  liste os 10 municipios com taxa de ocupacao acima de 1;
-- SELECT AI showsql quantos leitos SUS faltam em cada regiao para atingir a meta da OMS;
