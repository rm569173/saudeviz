"""
Camada de acesso a dados do SaudeViz.

A solucao foi desenhada para o Oracle Database (destino da camada Gold), mas o
MVP precisa rodar tambem em ambiente publico - o Streamlit Cloud, onde nao ha
tunel para o banco da faculdade. Por isso o acesso passa por uma interface
unica com duas implementacoes:

  MotorOracle  - python-oracledb em modo thin (sem Instant Client).
  MotorDuckDB  - arquivo local dados/saudeviz.duckdb, espelho do schema Oracle.

Ambos falam SQL ANSI sobre as mesmas tabelas T_SAUDE_*, entao as consultas do
painel e do Select AI sao as mesmas nos dois motores.
"""
from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

# Nome logico -> tabela fisica. Mantido igual nos dois motores.
TABELAS = {
    "dim_municipio": "T_SAUDE_DIM_MUNICIPIO",
    "dim_estabelecimento": "T_SAUDE_DIM_ESTABELECIMENTO",
    "fato_internacao_mensal": "T_SAUDE_FATO_INTERNACAO",
    "ind_capacidade_municipal": "T_SAUDE_IND_CAPACIDADE",
    "rank_hospitais": "T_SAUDE_RANK_HOSPITAIS",
    "serie_temporal_uf": "T_SAUDE_SERIE_UF",
    "previsao_internacoes": "T_SAUDE_PREVISAO",
    "cluster_municipios": "T_SAUDE_CLUSTER_MUNICIPIO",
}


class Motor(ABC):
    """Contrato minimo que o painel e o Select AI esperam de um banco."""

    nome: str

    @abstractmethod
    def consulta(self, sql: str) -> pd.DataFrame:
        """Executa um SELECT e devolve o resultado como DataFrame."""

    @abstractmethod
    def grava(self, df: pd.DataFrame, tabela: str) -> int:
        """Substitui o conteudo de uma tabela pelo DataFrame informado."""

    @abstractmethod
    def tabelas_existentes(self) -> list[str]:
        """Lista as tabelas do schema, usada para montar o prompt do NL->SQL."""

    def metadados(self) -> pd.DataFrame:
        """Colunas e tipos de todas as tabelas T_SAUDE_* (contexto do Select AI)."""
        linhas = []
        for tabela in self.tabelas_existentes():
            try:
                amostra = self.consulta(f"SELECT * FROM {tabela} WHERE 1=0")
            except Exception as erro:  # tabela ainda nao criada
                log.debug("Metadados indisponiveis para %s: %s", tabela, erro)
                continue
            for coluna, tipo in amostra.dtypes.items():
                linhas.append({"tabela": tabela, "coluna": coluna,
                               "tipo": str(tipo)})
        return pd.DataFrame(linhas)


class MotorDuckDB(Motor):
    """Data warehouse local em arquivo unico - usado pelo MVP publicado."""

    nome = "DuckDB (local)"

    def __init__(self, caminho: Path | None = None, somente_leitura: bool = False):
        import duckdb

        self._duckdb = duckdb
        self.caminho = Path(caminho or config.DUCKDB_PATH)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.somente_leitura = somente_leitura and self.caminho.exists()

    def _conecta(self):
        return self._duckdb.connect(str(self.caminho),
                                    read_only=self.somente_leitura)

    def consulta(self, sql: str) -> pd.DataFrame:
        with self._conecta() as con:
            return con.execute(sql).fetchdf()

    def grava(self, df: pd.DataFrame, tabela: str) -> int:
        with self._conecta() as con:
            con.register("_carga", df)
            con.execute(f"CREATE OR REPLACE TABLE {tabela} AS SELECT * FROM _carga")
            con.unregister("_carga")
        return len(df)

    def tabelas_existentes(self) -> list[str]:
        with self._conecta() as con:
            df = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name").fetchdf()
        return df["table_name"].tolist()


class MotorOracle(Motor):
    """
    Camada Gold no Oracle Database.

    Usa python-oracledb em modo thin: nao exige Oracle Instant Client
    instalado, o que simplifica a reproducao do projeto por terceiros.
    """

    nome = "Oracle Database"

    # Linhas por commit na carga. 10 mil equilibra o custo de ida e volta na
    # rede com o tamanho do rollback segment no servidor da faculdade.
    LOTE_PADRAO = 10_000

    def __init__(self, user: str | None = None, password: str | None = None,
                 dsn: str | None = None, lote: int | None = None):
        import oracledb

        self._oracledb = oracledb
        self.user = user or config.ORACLE_USER
        self.password = password or config.ORACLE_PASSWORD
        self.dsn = dsn or config.ORACLE_DSN
        self.lote = lote or self.LOTE_PADRAO
        if config.ORACLE_WALLET_DIR:
            oracledb.init_oracle_client(
                config_dir=config.ORACLE_WALLET_DIR)

    def _conecta(self):
        return self._oracledb.connect(user=self.user, password=self.password,
                                      dsn=self.dsn)

    def consulta(self, sql: str) -> pd.DataFrame:
        # O Oracle rejeita ";" no fim de um statement enviado via driver.
        sql = sql.strip().rstrip(";")
        with self._conecta() as con, con.cursor() as cur:
            cur.execute(sql)
            colunas = [d[0].lower() for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=colunas)

    @staticmethod
    def _para_tuplas(df: pd.DataFrame) -> list[tuple]:
        """
        Converte o DataFrame em tuplas que o driver consegue vincular.

        O oracledb nao sabe lidar com numpy.int64, numpy.nan nem pandas.NA.
        Converter para object devolve tipos nativos do Python, e o where()
        troca todos os ausentes por None, que o Oracle grava como NULL.
        """
        limpo = df.astype(object).where(pd.notna(df), None)
        return list(limpo.itertuples(index=False, name=None))

    def grava(self, df: pd.DataFrame, tabela: str) -> int:
        """
        Substitui o conteudo da tabela, inserindo em lotes.

        A carga vai por rede para um servidor academico compartilhado, entao
        mandar centenas de milhares de linhas num unico executemany seria
        lento, pesado em memoria e - o pior - impossivel de diagnosticar se
        falhasse no meio. Em lotes, cada commit e um ponto de progresso
        visivel no log.
        """
        colunas = list(df.columns)
        marcadores = ", ".join(f":{i + 1}" for i in range(len(colunas)))
        insert = (f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                  f"VALUES ({marcadores})")

        total = len(df)
        gravadas = 0
        with self._conecta() as con, con.cursor() as cur:
            try:
                cur.execute(f"TRUNCATE TABLE {tabela}")
            except self._oracledb.DatabaseError as erro:
                raise RuntimeError(
                    f"Nao foi possivel limpar {tabela}: {erro}. "
                    "Rode antes o script src/db/ddl_oracle.sql para criar as "
                    "tabelas T_SAUDE_*.") from erro

            for inicio in range(0, total, self.lote):
                fatia = df.iloc[inicio:inicio + self.lote]
                cur.executemany(insert, self._para_tuplas(fatia),
                                batcherrors=False)
                con.commit()
                gravadas += len(fatia)
                log.info("  %s: %s/%s linhas (%.0f%%)", tabela, gravadas,
                         total, 100 * gravadas / max(total, 1))
        return gravadas

    def tabelas_existentes(self) -> list[str]:
        df = self.consulta(
            "SELECT table_name FROM user_tables "
            "WHERE table_name LIKE 'T_SAUDE%' ORDER BY table_name")
        return df["table_name"].tolist()

    def select_ai_disponivel(self) -> bool:
        """Checa se o pacote DBMS_CLOUD_AI (Select AI) existe na instancia."""
        try:
            df = self.consulta(
                "SELECT COUNT(*) AS n FROM all_objects "
                "WHERE object_name = 'DBMS_CLOUD_AI'")
            return int(df.iloc[0, 0]) > 0
        except Exception as erro:
            log.info("Select AI indisponivel nesta instancia: %s", erro)
            return False


def obtem_motor(preferir_oracle: bool = True,
                somente_leitura: bool = False) -> Motor:
    """
    Devolve o motor disponivel, com Oracle como primeira opcao.

    Se as credenciais nao estiverem configuradas ou a conexao falhar, cai para
    o DuckDB local sem interromper a aplicacao - comportamento necessario para
    o painel publicado continuar funcionando fora da rede da faculdade.
    """
    if preferir_oracle and config.oracle_configurado():
        try:
            motor = MotorOracle()
            motor.consulta("SELECT 1 AS ok FROM dual")
            log.info("Conectado ao Oracle: %s", config.ORACLE_DSN)
            return motor
        except Exception as erro:
            log.warning("Oracle indisponivel (%s). Usando DuckDB local.", erro)
    return MotorDuckDB(somente_leitura=somente_leitura)
