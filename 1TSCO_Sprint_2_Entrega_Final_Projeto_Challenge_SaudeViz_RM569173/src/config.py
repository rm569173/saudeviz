"""
SaudeViz - Configuracao central do projeto.

Concentra caminhos, parametros de ingestao e credenciais (via variaveis de
ambiente) para que nenhum script precise de valores hardcoded.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Caminhos
# --------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
RAW = DADOS / "raw"        # arquivos originais baixados (.dbc/.json/.csv)
BRONZE = DADOS / "bronze"  # dado bruto convertido para parquet, sem tratamento
PRATA = DADOS / "prata"    # dado limpo, tipado e padronizado
OURO = DADOS / "ouro"      # tabelas analiticas agregadas (star schema)
EVIDENCIAS = RAIZ / "evidencias"

DIRETORIOS = (RAW, BRONZE, PRATA, OURO, EVIDENCIAS)


def prepara_diretorios() -> None:
    """
    Cria a arvore de diretorios de dados do projeto.

    Chamada explicitamente por quem escreve em disco, em vez de rodar como
    efeito colateral do import: importar um modulo de configuracao nao
    deveria alterar o sistema de arquivos.
    """
    for caminho in DIRETORIOS:
        caminho.mkdir(parents=True, exist_ok=True)


# Data warehouse local (DuckDB) - espelha o schema criado no Oracle
DUCKDB_PATH = DADOS / "saudeviz.duckdb"

# --------------------------------------------------------------------------
# Fonte 1 - SIH/SUS (estruturado, FTP DATASUS, formato .dbc)
# --------------------------------------------------------------------------
FTP_HOST = "ftp.datasus.gov.br"
FTP_DIR_SIH = "/dissemin/publicos/SIHSUS/200801_/Dados"

# Todas as unidades federativas publicadas pelo DATASUS.
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
]

# Recorte do MVP: Sudeste completo, ~89 milhoes de habitantes. As quatro UFs
# trocam pacientes entre si, o que da sentido a analise de transferencias.
UFS_MVP = ["ES", "MG", "RJ", "SP"]

UFS = UFS_MVP

# --------------------------------------------------------------------------
# Dimensao temporal: competencia x data de internacao
# --------------------------------------------------------------------------
# ANO_CMPT/MES_CMPT e o mes em que a AIH foi paga, nao o da internacao: a
# competencia 202401 traz 41,7% de internacoes de 2023. A defasagem chega a
# 3 meses, entao a ingestao vai ate marco/2025 para fechar dezembro/2024.
ANO_INICIO, MES_INICIO = 2024, 1
ANO_FIM, MES_FIM = 2025, 3

# Ano civil analisado, recortado por dt_internacao (e nao por competencia).
ANO_ANALISE = 2024

# Colunas usadas, das 113 do SIH. A selecao foi conferida no preenchimento de
# MG e AC: as descartadas estao vazias ou constantes nos dois estados.
COLUNAS_SIH = [
    "N_AIH",       # identificador da internacao
    "ANO_CMPT",    # ano de competencia
    "MES_CMPT",    # mes de competencia
    "UF_ZI",       # UF/gestor
    "MUNIC_RES",   # municipio de residencia do paciente
    "MUNIC_MOV",   # municipio onde ocorreu o atendimento
    "CNES",        # estabelecimento (chave de ligacao com a fonte CNES)
    "ESPEC",       # especialidade do leito
    "CAR_INT",     # carater da internacao (eletiva/urgencia)
    "COMPLEX",     # complexidade (media/alta)
    "PROC_REA",    # procedimento realizado
    "DIAG_PRINC",  # CID-10 principal
    "DT_INTER",    # data de internacao
    "DT_SAIDA",    # data de saida
    "DIAS_PERM",   # dias de permanencia
    "QT_DIARIAS",  # quantidade de diarias
    "UTI_MES_TO",  # diarias de UTI
    "MORTE",       # obito
    "IDADE",       # idade
    "COD_IDADE",   # unidade da idade (2=dias,3=meses,4=anos)
    "SEXO",        # sexo
    "RACA_COR",    # raca/cor
    "VAL_TOT",     # valor total da AIH
    "VAL_UTI",     # valor de UTI
    # --- desfecho da internacao ---------------------------------------
    "COBRANCA",    # motivo de saida: alta, permanencia, transferencia, obito
    "IDENT",       # 1 = AIH normal, 5 = longa permanencia
    # --- decomposicao financeira ---------------------------------------
    "VAL_SH",      # valor de servicos hospitalares (estrutura)
    "VAL_SP",      # valor de servicos profissionais (equipe)
    "FINANC",      # tipo de financiamento: 06 = MAC, 04 = FAEC
    # --- perfil do prestador e do caso ---------------------------------
    "NAT_JUR",     # natureza juridica do prestador (publico/privado/filantropico)
    "MARCA_UTI",   # tipo de UTI utilizada
    "DIAGSEC1",    # diagnostico secundario (comorbidade)
    "PROC_SOLIC",  # procedimento solicitado (comparar com PROC_REA)
]

# --------------------------------------------------------------------------
# Fonte 2 - CNES (semiestruturado, API REST JSON)
# --------------------------------------------------------------------------
API_CNES = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
API_CNES_LIMITE_PAGINA = 20      # limite maximo aceito pelo endpoint
API_CNES_PAUSA_SEG = 0.15        # cortesia entre requisicoes

# --------------------------------------------------------------------------
# Fonte 3 - IBGE (CSV -> External Table no Oracle)
# --------------------------------------------------------------------------
API_IBGE_POP = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/"
    "{ano}/variaveis/9324?localidades=N6[all]"
)
API_IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
ANO_POPULACAO = 2024
CSV_POPULACAO = RAW / "populacao_municipios.csv"

# --------------------------------------------------------------------------
# Oracle (opcional) - preenchido por variaveis de ambiente
# --------------------------------------------------------------------------
ORACLE_USER = os.getenv("ORACLE_USER", "")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
ORACLE_WALLET_DIR = os.getenv("ORACLE_WALLET_DIR", "")

ORACLE_HOST = os.getenv("ORACLE_HOST", "oracle.fiap.com.br")
ORACLE_PORTA = int(os.getenv("ORACLE_PORTA", "1521"))
ORACLE_SID = os.getenv("ORACLE_SID", "orcl")

# A instancia da FIAP e identificada por SID, nao por service name. O formato
# curto "host:porta/nome" (easy connect) assume service name e falharia aqui,
# entao montamos o connect descriptor completo com CONNECT_DATA=(SID=...).
ORACLE_DSN = os.getenv(
    "ORACLE_DSN",
    f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={ORACLE_HOST})"
    f"(PORT={ORACLE_PORTA}))(CONNECT_DATA=(SID={ORACLE_SID})))",
)

def oracle_configurado() -> bool:
    """Indica se ha credenciais suficientes para tentar conexao com o Oracle."""
    return bool(ORACLE_USER and ORACLE_PASSWORD and ORACLE_DSN)

# --------------------------------------------------------------------------
# Parametros de negocio
# --------------------------------------------------------------------------
# Referencia OMS: 300 leitos por 100 mil habitantes.
LEITOS_POR_100MIL_OMS = 300
# Limite acima do qual a regiao entra em alerta de pressao assistencial.
LIMITE_PRESSAO_ALERTA = 1.0
