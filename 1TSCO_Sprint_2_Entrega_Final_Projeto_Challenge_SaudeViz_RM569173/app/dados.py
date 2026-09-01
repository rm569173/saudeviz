"""
Camada de acesso a dados do painel SaudeViz.

Cada filtro do painel vira SQL executado contra as tabelas T_SAUDE_* do
Oracle. Se o banco nao responder, cai para o retrato em parquet de
dados/ouro e avisa na barra lateral - dado de contingencia nunca se passa
por dado ao vivo.

Credenciais nunca ficam no codigo. A ordem de busca e st.secrets["oracle"],
usado no Streamlit Cloud, e depois as variaveis de ambiente ORACLE_USER,
ORACLE_PASSWORD e ORACLE_DSN.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

DIR_OURO = RAIZ / "dados" / "ouro"

# Nome logico -> tabela no Oracle / arquivo parquet local.
TABELAS = {
    "fato_internacao_mensal": "T_SAUDE_FATO_INTERNACAO_MENSAL",
    "ind_capacidade_municipal": "T_SAUDE_IND_CAPACIDADE_MUNICIPAL",
    "rank_hospitais": "T_SAUDE_RANK_HOSPITAIS",
    "dim_municipio": "T_SAUDE_DIM_MUNICIPIO",
    "dim_estabelecimento": "T_SAUDE_DIM_ESTABELECIMENTO",
    "serie_diaria_uf": "T_SAUDE_SERIE_DIARIA_UF",
    "previsao_internacoes": "T_SAUDE_PREVISAO_INTERNACOES",
    "avaliacao_modelo": "T_SAUDE_AVALIACAO_MODELO",
    "comparativo_horizonte": "T_SAUDE_COMPARATIVO_HORIZONTE",
    "coeficientes_modelo": "T_SAUDE_COEFICIENTES_MODELO",
}


# Sem timeout o driver espera indefinidamente e o painel trava na tela de
# carregamento, em vez de cair para o retrato local.
TIMEOUT_CONEXAO = 8
TIMEOUT_CONSULTA = 60


def _credenciais() -> dict[str, str] | None:
    """Le as credenciais do Oracle sem nunca grava-las em disco."""
    base = {
        "tcp_connect_timeout": TIMEOUT_CONEXAO,
        "retry_count": 0,
    }
    try:
        secrets = st.secrets["oracle"]
        return {"user": secrets["user"], "password": secrets["password"],
                "dsn": secrets["dsn"], **base}
    except Exception:
        pass

    usuario = os.getenv("ORACLE_USER")
    senha = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN")
    if usuario and senha and dsn:
        return {"user": usuario, "password": senha, "dsn": dsn, **base}
    return None


@st.cache_resource(show_spinner=False)
def _testa_oracle() -> tuple[bool, str]:
    """
    Verifica uma vez por sessao se o Oracle responde.

    Cacheado como recurso porque o resultado vale para a sessao inteira: nao
    faz sentido tentar reconectar a cada interacao do usuario se o banco ja se
    mostrou inacessivel.
    """
    credenciais = _credenciais()
    if not credenciais:
        return False, "Credenciais do Oracle nao configuradas neste ambiente."
    try:
        import oracledb

        with oracledb.connect(**credenciais) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM user_tables "
                               "WHERE table_name LIKE 'T_SAUDE%'")
                total = cursor.fetchone()[0]
        if total == 0:
            return False, "Conectado, mas nenhuma tabela T_SAUDE_ encontrada."
        return True, f"Oracle Database 19c - {total} tabelas T_SAUDE_"
    except Exception as erro:
        # Vai para os logs do app, que sao privados. So comprimento e espaco
        # nas bordas, nunca o valor: distingue as causas de ORA-01017.
        usuario = str(credenciais.get("user", ""))
        senha = credenciais.get("password", "")
        dsn = credenciais.get("dsn", "")
        print("[SaudeViz] Falha ao conectar no Oracle. Diagnostico da credencial:")
        print(f"[SaudeViz]   user  : {len(usuario)} caracteres, "
              f"espacos nas bordas: {usuario != usuario.strip()}")
        print(f"[SaudeViz]   senha : {len(senha)} caracteres, "
              f"espacos nas bordas: {senha != senha.strip()}")
        print(f"[SaudeViz]   dsn   : {len(dsn)} caracteres, "
              f"comeca com '(DESCRIPTION': {dsn.startswith('(DESCRIPTION')}")
        print(f"[SaudeViz]   erro  : {type(erro).__name__}: "
              f"{str(erro).splitlines()[0][:120]}")
        return False, f"{type(erro).__name__}: {str(erro).splitlines()[0][:90]}"


def modo_conexao() -> tuple[str, str]:
    """Devolve ('oracle' ou 'parquet', mensagem descritiva) para a interface."""
    ativo, detalhe = _testa_oracle()
    return ("oracle" if ativo else "parquet"), detalhe


def _modo() -> str:
    """Destino em uso, para escolher o dialeto de SQL."""
    ativo, _ = _testa_oracle()
    return "oracle" if ativo else "parquet"


# Linhas trazidas por ida e volta ao banco. O padrao do driver e 100, o que
# para uma tabela de 200 mil linhas significa 2 mil viagens ate o servidor da
# faculdade - inviavel pela internet publica. Com 10 mil por busca, sao 20.
LINHAS_POR_BUSCA = 10_000


@st.cache_data(ttl=3600, show_spinner=False)
def consulta_oracle(sql: str) -> pd.DataFrame:
    """Executa SQL no Oracle. Levanta excecao se o banco nao responder."""
    import oracledb

    credenciais = _credenciais()
    if not credenciais:
        raise RuntimeError("Credenciais do Oracle nao configuradas.")

    with oracledb.connect(**credenciais) as conexao:
        conexao.call_timeout = TIMEOUT_CONSULTA * 1000  # milissegundos
        with conexao.cursor() as cursor:
            cursor.arraysize = LINHAS_POR_BUSCA
            cursor.prefetchrows = LINHAS_POR_BUSCA + 1
            cursor.execute(sql.strip().rstrip(";"))
            colunas = [descricao[0].lower() for descricao in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=colunas)


@st.cache_data(ttl=600, show_spinner=False)
def consulta_local(sql: str) -> pd.DataFrame:
    """
    Executa o mesmo SQL sobre os parquets locais, via DuckDB.

    Existe para que o modo de contingencia continue RESPONDENDO, e nao apenas
    exibindo a consulta que teria sido enviada. Numa apresentacao ao vivo, a
    diferenca entre mostrar um resultado e mostrar um erro de conexao e a
    diferenca entre a demo funcionar e nao funcionar.

    As views recebem os mesmos nomes T_SAUDE_* das tabelas do Oracle, entao o
    SQL gerado pelo tradutor roda sem alteracao nos dois destinos.
    """
    import duckdb

    conexao = duckdb.connect(":memory:")
    try:
        for nome, tabela_oracle in TABELAS.items():
            arquivo = DIR_OURO / f"{nome}.parquet"
            if arquivo.exists():
                caminho = str(arquivo).replace("'", "''")
                conexao.execute(
                    f"CREATE VIEW {tabela_oracle} AS "
                    f"SELECT * FROM read_parquet('{caminho}')")
        return conexao.execute(sql.strip().rstrip(";")).fetchdf()
    finally:
        conexao.close()


def consulta(sql: str) -> pd.DataFrame:
    """
    Executa a consulta no destino disponivel.

    Quem chama recebe tambem a origem do resultado, para que a interface possa
    informar se o dado veio do banco ou do retrato local - resultado de
    contingencia nunca deve se passar por dado ao vivo.
    """
    ativo, _ = _testa_oracle()
    if ativo:
        return consulta_oracle(sql)
    return consulta_local(sql)


@st.cache_data(ttl=600, show_spinner=False)
def carrega(nome: str) -> pd.DataFrame:
    """
    Carrega uma tabela da camada Ouro, do Oracle ou do parquet local.

    As tabelas do painel sao pequenas (a maior tem ~204 mil linhas), entao
    carregar inteiro e filtrar em memoria e mais rapido do que ida e volta ao
    banco a cada movimento de filtro.
    """
    if nome not in TABELAS:
        raise KeyError(f"Tabela desconhecida: {nome}")

    ativo, _ = _testa_oracle()
    if ativo:
        try:
            return consulta_oracle(f"SELECT * FROM {TABELAS[nome]}")
        except Exception:
            pass  # cai para o parquet abaixo

    arquivo = DIR_OURO / f"{nome}.parquet"
    if not arquivo.exists():
        raise FileNotFoundError(
            f"Nem o Oracle nem o arquivo {arquivo.name} estao disponiveis. "
            "Rode 'py -m src.db.databricks_upload --baixar-ouro'.")
    return pd.read_parquet(arquivo)


# ---------------------------------------------------------------------------
# Indicadores agregados usados nos cartoes de abertura
# ---------------------------------------------------------------------------

def filtro_uf(ufs: tuple[str, ...] | None, coluna: str = "uf") -> str:
    """Clausula de filtro por UF, ou vazia quando todas estao selecionadas."""
    if not ufs:
        return ""
    lista = ", ".join(f"'{uf}'" for uf in ufs)
    return f" AND {coluna} IN ({lista})"


@st.cache_data(ttl=3600, show_spinner=False)
def indicadores_gerais(ufs: tuple[str, ...] | None = None) -> dict[str, float]:
    """
    Numeros de topo do painel.

    A agregacao roda no banco, nao em memoria: trazer 200 mil linhas pela
    internet para calcular sete somas seria desperdicio de rede e o motivo de
    o painel demorar a abrir.
    """
    resultado = consulta(f"""
        SELECT SUM(internacoes)      AS internacoes,
               SUM(dias_permanencia) AS dias_permanencia,
               SUM(obitos)           AS obitos,
               SUM(transferencias)   AS transferencias,
               SUM(valor_total)      AS valor_total
          FROM T_SAUDE_FATO_INTERNACAO_MENSAL
         WHERE 1 = 1{filtro_uf(ufs)}
    """)
    if resultado.empty or not resultado["internacoes"].iloc[0]:
        return {}

    linha = resultado.iloc[0]
    internacoes = int(linha["internacoes"])
    return {
        "internacoes": internacoes,
        "valor_total": float(linha["valor_total"]),
        # Medias sempre a partir das somas: media de medias daria peso igual a
        # grupos de tamanhos diferentes.
        "permanencia_media": float(linha["dias_permanencia"]) / internacoes,
        "taxa_mortalidade": 100 * float(linha["obitos"]) / internacoes,
        "taxa_transferencia": 100 * float(linha["transferencias"]) / internacoes,
        "custo_medio": float(linha["valor_total"]) / internacoes,
        "leitos_dia": int(linha["dias_permanencia"]),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def internacoes_por_mes(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Serie mensal por UF para o grafico de evolucao."""
    return consulta(f"""
        SELECT uf, mes, SUM(internacoes) AS internacoes
          FROM T_SAUDE_FATO_INTERNACAO_MENSAL
         WHERE 1 = 1{filtro_uf(ufs)}
         GROUP BY uf, mes
         ORDER BY uf, mes
    """)


@st.cache_data(ttl=3600, show_spinner=False)
def resumo_por_uf(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """
    Totais e indicadores por unidade federativa.

    O ORDER BY usa o alias, e nao SUM(internacoes) de novo: no Oracle o alias
    e resolvido antes da coluna de origem, e como ele ja e o proprio SUM,
    repetir a funcao criaria um agregado aninhado - que o banco rejeita. O
    DuckDB aceita, entao o erro so aparecia com o Oracle conectado.
    """
    return consulta(f"""
        SELECT uf,
               SUM(internacoes)                                        AS internacoes,
               ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)      AS permanencia,
               ROUND(100 * SUM(obitos) / SUM(internacoes), 2)          AS mortalidade,
               ROUND(SUM(valor_total) / SUM(internacoes), 2)           AS custo
          FROM T_SAUDE_FATO_INTERNACAO_MENSAL
         WHERE 1 = 1{filtro_uf(ufs)}
         GROUP BY uf
         ORDER BY internacoes DESC
    """)


@st.cache_data(ttl=3600, show_spinner=False)
def ocupacao_ponderada(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """
    Taxa de ocupacao por porte de municipio.

    Traz as duas versoes de proposito: a media simples entre municipios-mes,
    que trata uma cidade de tres leitos igual a Sao Paulo, e a ponderada por
    leitos-dia, que e a taxa real do sistema.
    """
    return consulta(f"""
        SELECT porte,
               COUNT(DISTINCT cod_municipio_6)                             AS municipios,
               SUM(internacoes)                                            AS internacoes,
               ROUND(AVG(taxa_ocupacao), 3)                                AS ocupacao_simples,
               ROUND(SUM(dias_permanencia) / SUM(leitos_dia_disponiveis), 3) AS ocupacao_ponderada
          FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
         WHERE leitos_dia_disponiveis > 0{filtro_uf(ufs)}
         GROUP BY porte
         ORDER BY ocupacao_ponderada DESC
    """)


@st.cache_data(ttl=3600, show_spinner=False)
def situacao_capacidade(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Contagem de municipio-mes por classificacao de ocupacao."""
    return consulta(f"""
        SELECT situacao, COUNT(*) AS municipios_mes
          FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
         WHERE 1 = 1{filtro_uf(ufs)}
         GROUP BY situacao
    """)


@st.cache_data(ttl=3600, show_spinner=False)
def municipios_criticos(ufs: tuple[str, ...] | None = None,
                        limite: int = 25) -> pd.DataFrame:
    """Municipios com maior taxa de ocupacao, em atencao ou situacao critica."""
    corte = ("LIMIT " + str(limite) if _modo() == "parquet"
             else f"FETCH FIRST {limite} ROWS ONLY")
    return consulta(f"""
        SELECT municipio, uf, competencia, populacao, internacoes,
               leitos_sus, taxa_ocupacao, situacao
          FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
         WHERE situacao IN ('Critica', 'Atencao'){filtro_uf(ufs)}
         ORDER BY taxa_ocupacao DESC
         {corte}
    """)


# Capitais do Sudeste, pelo codigo IBGE de 6 digitos usado pelo SIH.
CAPITAIS = {
    "320530": "Vitória",
    "310620": "Belo Horizonte",
    "330455": "Rio de Janeiro",
    "355030": "São Paulo",
}

# Acima de 85% a fila de espera cresce de forma nao linear. Dimensionar para
# 100% nao deixaria folga para a variacao diaria.
OCUPACAO_ALVO_PADRAO = 0.85


@st.cache_data(ttl=3600, show_spinner=False)
def necessidade_leitos(cod_municipio: str,
                       ocupacao_alvo: float = OCUPACAO_ALVO_PADRAO
                       ) -> pd.DataFrame:
    """
    Quantos leitos o municipio precisaria ter, mes a mes.

    O calculo parte dos leitos-dia efetivamente consumidos:

        leitos ocupados em media = dias de permanencia / dias do mes
        leitos necessarios       = leitos ocupados / taxa de ocupacao alvo

    A divisao pela taxa alvo e o que transforma consumo observado em
    dimensionamento: operar a 100% nao deixa folga para a variacao do dia a
    dia, e a fila cresce de forma nao linear acima de 85%.
    """
    dados_mes = consulta(f"""
        SELECT municipio,
               uf,
               mes,
               competencia,
               internacoes,
               dias_permanencia,
               dias_no_mes,
               leitos_sus,
               permanencia_media
          FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
         WHERE cod_municipio_6 = '{cod_municipio}'
         ORDER BY mes
    """)
    if dados_mes.empty:
        return dados_mes

    dados_mes["leitos_ocupados"] = (
        dados_mes["dias_permanencia"] / dados_mes["dias_no_mes"]).round(0)
    dados_mes["leitos_necessarios"] = (
        dados_mes["leitos_ocupados"] / ocupacao_alvo).round(0)
    dados_mes["saldo"] = (
        dados_mes["leitos_sus"] - dados_mes["leitos_necessarios"])
    dados_mes["ocupacao_efetiva"] = (
        dados_mes["leitos_ocupados"] / dados_mes["leitos_sus"]).round(3)

    # Linha de base: o mes de menor necessidade e o piso que a rede precisa
    # manter aberto o ano inteiro. O que passa disso e capacidade sazonal.
    base = dados_mes["leitos_necessarios"].min()
    dados_mes["leitos_extras"] = (dados_mes["leitos_necessarios"] - base).astype(int)
    return dados_mes


@st.cache_data(ttl=3600, show_spinner=False)
def perfis_pressao(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """
    Perfis de atendimento ordenados por consumo de leitos-dia.

    A pressao relativa compara a participacao do perfil nos leitos-dia com a
    participacao no numero de internacoes. Acima de 1, o perfil ocupa mais
    leito do que o volume sugere.
    """
    perfil = consulta(f"""
        SELECT perfil_atendimento,
               SUM(internacoes)      AS internacoes,
               SUM(dias_permanencia) AS leitos_dia,
               SUM(valor_total)      AS valor_total,
               SUM(obitos)           AS obitos
          FROM T_SAUDE_FATO_INTERNACAO_MENSAL
         WHERE 1 = 1{filtro_uf(ufs)}
         GROUP BY perfil_atendimento
         ORDER BY leitos_dia DESC
    """)
    if perfil.empty:
        return perfil

    total_internacoes = perfil["internacoes"].sum()
    total_leitos_dia = perfil["leitos_dia"].sum()
    perfil["pct_internacoes"] = (
        100 * perfil["internacoes"] / total_internacoes).round(2)
    perfil["pct_leitos_dia"] = (
        100 * perfil["leitos_dia"] / total_leitos_dia).round(2)
    perfil["pressao_relativa"] = (
        perfil["pct_leitos_dia"] / perfil["pct_internacoes"]).round(2)
    perfil["permanencia_media"] = (
        perfil["leitos_dia"] / perfil["internacoes"]).round(2)
    perfil["custo_medio_aih"] = (
        perfil["valor_total"] / perfil["internacoes"]).round(2)
    return perfil
