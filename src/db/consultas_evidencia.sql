-- ===========================================================================
-- SaudeViz - Consultas de evidencia da camada Gold no Oracle
-- Challenge FIAP x Oracle 2026 - 1TSCOA
-- Lucas Ventura Araujo Ribas Colen - RM 569173
--
-- Abra este arquivo no SQL Developer conectado como RM569173 e execute cada
-- bloco com Ctrl+Enter (posicione o cursor dentro do comando).
--
-- Cada consulta produz um print para a apresentacao. O nome do arquivo
-- sugerido esta no comentario de cada bloco.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. As tabelas da camada Gold existem no Oracle, e com quantas linhas
--    print: oracle_tabelas.png
--
-- Usa COUNT(*) real em vez de USER_TABLES.NUM_ROWS: essa coluna do dicionario
-- so e preenchida depois que o otimizador coleta estatisticas, e viria vazia
-- numa carga recente.
-- ---------------------------------------------------------------------------
SELECT 'T_SAUDE_DIM_MUNICIPIO'            AS tabela, COUNT(*) AS linhas FROM t_saude_dim_municipio
UNION ALL
SELECT 'T_SAUDE_DIM_ESTABELECIMENTO',              COUNT(*) FROM t_saude_dim_estabelecimento
UNION ALL
SELECT 'T_SAUDE_FATO_INTERNACAO_MENSAL',           COUNT(*) FROM t_saude_fato_internacao_mensal
UNION ALL
SELECT 'T_SAUDE_IND_CAPACIDADE_MUNICIPAL',         COUNT(*) FROM t_saude_ind_capacidade_municipal
UNION ALL
SELECT 'T_SAUDE_RANK_HOSPITAIS',                   COUNT(*) FROM t_saude_rank_hospitais
UNION ALL
SELECT 'T_SAUDE_SERIE_TEMPORAL_UF',                COUNT(*) FROM t_saude_serie_temporal_uf
UNION ALL
SELECT 'T_SAUDE_SERIE_DIARIA_UF',                  COUNT(*) FROM t_saude_serie_diaria_uf
UNION ALL
SELECT 'T_SAUDE_PREVISAO_INTERNACOES',             COUNT(*) FROM t_saude_previsao_internacoes
UNION ALL
SELECT 'T_SAUDE_AVALIACAO_MODELO',                 COUNT(*) FROM t_saude_avaliacao_modelo
ORDER BY 2 DESC;


-- ---------------------------------------------------------------------------
-- 2. Os metadados que alimentam o tradutor de linguagem natural
--    print: oracle_comentarios.png
--
-- Esta e a consulta mais importante desta serie. Os COMMENT ON abaixo sao
-- exatamente o insumo que o Select AI do Autonomous Database consumiria para
-- traduzir portugues em SQL - e sao os mesmos que o nosso tradutor usa.
-- Por isso estao escritos em linguagem de negocio, e nao em jargao tecnico.
-- ---------------------------------------------------------------------------
SELECT table_name  AS tabela,
       comments    AS descricao_de_negocio
  FROM user_tab_comments
 WHERE table_name LIKE 'T_SAUDE%'
   AND comments IS NOT NULL
 ORDER BY table_name;


-- ---------------------------------------------------------------------------
-- 3. Consulta de negocio: os maiores hospitais do Sudeste
--    print: oracle_consulta_negocio.png
-- ---------------------------------------------------------------------------
SELECT ranking_regional        AS pos,
       nome_fantasia           AS hospital,
       uf,
       esfera,
       internacoes,
       leitos_sus,
       permanencia_media,
       giro_leito_ano,
       taxa_transferencia
  FROM t_saude_rank_hospitais
 ORDER BY internacoes DESC
 FETCH FIRST 10 ROWS ONLY;


-- ---------------------------------------------------------------------------
-- 4. Onde a capacidade foi ultrapassada
--    print opcional: oracle_municipios_criticos.png
-- ---------------------------------------------------------------------------
SELECT municipio,
       uf,
       competencia,
       populacao,
       internacoes,
       leitos_sus,
       taxa_ocupacao,
       situacao
  FROM t_saude_ind_capacidade_municipal
 WHERE situacao = 'Critica'
 ORDER BY taxa_ocupacao DESC
 FETCH FIRST 15 ROWS ONLY;


-- ---------------------------------------------------------------------------
-- 5. Quais perfis de atendimento mais pressionam o sistema
--    print opcional: oracle_perfis_pressao.png
--
-- A ordenacao e por leitos-dia consumidos, nao por numero de internacoes:
-- volume alto com permanencia curta pressiona menos que volume baixo com
-- permanencia longa.
-- ---------------------------------------------------------------------------
SELECT perfil_atendimento,
       SUM(internacoes)                                        AS internacoes,
       SUM(dias_permanencia)                                   AS leitos_dia,
       ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)      AS permanencia_media,
       ROUND(100 * SUM(dias_permanencia)
             / SUM(SUM(dias_permanencia)) OVER (), 1)          AS pct_leitos_dia,
       ROUND(SUM(valor_total) / SUM(internacoes), 2)           AS custo_medio_aih
  FROM t_saude_fato_internacao_mensal
 GROUP BY perfil_atendimento
 ORDER BY leitos_dia DESC
 FETCH FIRST 10 ROWS ONLY;


-- ---------------------------------------------------------------------------
-- 6. Conferencia de integridade: os totais batem entre as tabelas
--    print opcional: oracle_integridade.png
--
-- As tres tabelas foram construidas por caminhos diferentes a partir da mesma
-- camada Prata. Se os totais coincidem, a modelagem esta consistente.
-- ---------------------------------------------------------------------------
SELECT 'Fato de internacoes'        AS origem, SUM(internacoes) AS internacoes
  FROM t_saude_fato_internacao_mensal
UNION ALL
SELECT 'Indicador de capacidade',            SUM(internacoes)
  FROM t_saude_ind_capacidade_municipal
UNION ALL
SELECT 'Ranking de hospitais',               SUM(internacoes)
  FROM t_saude_rank_hospitais;
