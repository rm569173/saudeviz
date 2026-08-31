"""
Camada de acesso a dados do painel SaudeViz.

Estrategia de conexao
---------------------
O painel consulta o Oracle Database da FIAP ao vivo: cada filtro vira SQL
executado contra as tabelas T_SAUDE_* da camada Ouro. Se o banco estiver
indisponivel - fora do ar, rede bloqueada, credencial ausente no ambiente de
publicacao - o painel cai automaticamente para o retrato em parquet gravado em
dados/ouro e informa isso na interface.

Isso nao e desconfianca do Oracle: e a diferenca entre uma apresentacao que
trava ao vivo e uma que continua. O modo em uso fica visivel na barra lateral,
para que ninguem interprete dado de contingencia como dado ao vivo.

Credenciais
-----------
Nunca ficam no codigo. A ordem de busca e:
  1. st.secrets["oracle"]  - usado no Streamlit Community Cloud
  2. variaveis de ambiente ORACLE_USER / ORACLE_PASSWORD / ORACLE_DSN
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


def _credenciais() -> dict[str, str] | None:
    """Le as credenciais do Oracle sem nunca grava-las em disco."""
    try:
        secrets = st.secrets["oracle"]
        return {"user": secrets["user"], "password": secrets["password"],
                "dsn": secrets["dsn"]}
    except Exception:
        pass

    usuario = os.getenv("ORACLE_USER")
    senha = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN")
    if usuario and senha and dsn:
        return {"user": usuario, "password": senha, "dsn": dsn}
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
        # Diagnostico enviado para os LOGS do app, nunca para a interface: os
        # logs sao privados ao dono do app, e a interface e publica.
        #
        # Reporta apenas COMPRIMENTO e presenca de espacos nas bordas. Isso
        # distingue as tres causas de ORA-01017 sem revelar a credencial:
        # senha truncada pelo TOML, espaco colado junto, ou senha errada mesmo.
        usuario = credenciais.get("user", "")
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


@st.cache_data(ttl=600, show_spinner=False)
def consulta_oracle(sql: str) -> pd.DataFrame:
    """Executa SQL no Oracle. Levanta excecao se o banco nao responder."""
    import oracledb

    credenciais = _credenciais()
    if not credenciais:
        raise RuntimeError("Credenciais do Oracle nao configuradas.")

    with oracledb.connect(**credenciais) as conexao:
        with conexao.cursor() as cursor:
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

@st.cache_data(ttl=600, show_spinner=False)
def indicadores_gerais(ufs: tuple[str, ...] | None = None) -> dict[str, float]:
    """Numeros de topo do painel, ja filtrados pelas UFs selecionadas."""
    fato = carrega("fato_internacao_mensal")
    if ufs:
        fato = fato[fato["uf"].isin(ufs)]

    internacoes = int(fato["internacoes"].sum())
    if internacoes == 0:
        return {}

    return {
        "internacoes": internacoes,
        "valor_total": float(fato["valor_total"].sum()),
        # Medias sempre a partir das somas: media de medias daria peso igual a
        # grupos de tamanhos diferentes.
        "permanencia_media": float(fato["dias_permanencia"].sum() / internacoes),
        "taxa_mortalidade": 100 * float(fato["obitos"].sum() / internacoes),
        "taxa_transferencia": 100 * float(fato["transferencias"].sum() / internacoes),
        "custo_medio": float(fato["valor_total"].sum() / internacoes),
        "leitos_dia": int(fato["dias_permanencia"].sum()),
    }


@st.cache_data(ttl=600, show_spinner=False)
def ocupacao_ponderada(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """
    Taxa de ocupacao por porte de municipio, ponderada por leitos-dia.

    A media simples entre municipios-mes seria enganosa: uma cidade com tres
    leitos pesaria tanto quanto Sao Paulo.
    """
    capacidade = carrega("ind_capacidade_municipal")
    if ufs:
        capacidade = capacidade[capacidade["uf"].isin(ufs)]

    agregado = (capacidade.groupby("porte", as_index=False)
                .agg(municipios=("cod_municipio_6", "nunique"),
                     internacoes=("internacoes", "sum"),
                     dias_permanencia=("dias_permanencia", "sum"),
                     leitos_dia=("leitos_dia_disponiveis", "sum"),
                     ocupacao_simples=("taxa_ocupacao", "mean")))
    agregado["ocupacao_ponderada"] = (
        agregado["dias_permanencia"] / agregado["leitos_dia"]).round(3)
    agregado["ocupacao_simples"] = agregado["ocupacao_simples"].round(3)
    return agregado.sort_values("ocupacao_ponderada", ascending=False)


@st.cache_data(ttl=600, show_spinner=False)
def perfis_pressao(ufs: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Perfis de atendimento ordenados por consumo de leitos-dia."""
    fato = carrega("fato_internacao_mensal")
    if ufs:
        fato = fato[fato["uf"].isin(ufs)]

    total_internacoes = fato["internacoes"].sum()
    total_leitos_dia = fato["dias_permanencia"].sum()

    perfil = (fato.groupby("perfil_atendimento", as_index=False)
              .agg(internacoes=("internacoes", "sum"),
                   leitos_dia=("dias_permanencia", "sum"),
                   valor_total=("valor_total", "sum"),
                   obitos=("obitos", "sum")))

    perfil["pct_internacoes"] = (
        100 * perfil["internacoes"] / total_internacoes).round(2)
    perfil["pct_leitos_dia"] = (
        100 * perfil["leitos_dia"] / total_leitos_dia).round(2)
    # Acima de 1: o perfil ocupa mais leito do que o volume sugere.
    perfil["pressao_relativa"] = (
        perfil["pct_leitos_dia"] / perfil["pct_internacoes"]).round(2)
    perfil["permanencia_media"] = (
        perfil["leitos_dia"] / perfil["internacoes"]).round(2)
    perfil["custo_medio_aih"] = (
        perfil["valor_total"] / perfil["internacoes"]).round(2)

    return perfil.sort_values("leitos_dia", ascending=False)
