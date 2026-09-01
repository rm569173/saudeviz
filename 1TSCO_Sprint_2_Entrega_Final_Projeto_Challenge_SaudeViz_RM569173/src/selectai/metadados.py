"""
Catalogo de metadados das tabelas T_SAUDE_*.

Este modulo e a peca que espelha o Select AI da Oracle. O Select AI le os
COMMENT ON TABLE e COMMENT ON COLUMN do dicionario de dados para entender o
que cada tabela significa antes de gerar SQL; nosso tradutor faz o mesmo.

Por isso os comentarios das tabelas foram escritos em linguagem de negocio, e
nao em jargao tecnico: eles sao o contexto do tradutor, e a portabilidade para
o Autonomous Database depende deles - trocar de motor de traducao nao exige
remodelar nada.
"""
from __future__ import annotations

import logging
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

log = logging.getLogger(__name__)


def normaliza(texto: str) -> str:
    """Minusculas sem acento, para comparar texto digitado com o vocabulario."""
    if not isinstance(texto, str):
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower().strip()


@dataclass
class Coluna:
    nome: str
    descricao: str
    sinonimos: tuple[str, ...] = ()


@dataclass
class Tabela:
    nome: str
    descricao: str
    granularidade: str
    colunas: list[Coluna] = field(default_factory=list)

    def descreve(self) -> str:
        """Texto do dicionario, usado no painel e como contexto do tradutor."""
        linhas = [f"{self.nome} — {self.descricao}",
                  f"  Granularidade: {self.granularidade}"]
        for coluna in self.colunas:
            linhas.append(f"    {coluna.nome:26s} {coluna.descricao}")
        return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Dicionario de dados da camada Gold
#
# Espelha os COMMENT ON gravados no Oracle pelos notebooks 03 e 05. Mantido
# tambem em codigo para que o painel funcione offline, no modo de contingencia
# em que o banco da faculdade esta indisponivel.
# ---------------------------------------------------------------------------
CATALOGO: dict[str, Tabela] = {
    "T_SAUDE_FATO_INTERNACAO_MENSAL": Tabela(
        nome="T_SAUDE_FATO_INTERNACAO_MENSAL",
        descricao=("Internacoes do SIH/SUS agregadas por municipio de "
                   "atendimento, mes de internacao, perfil de atendimento, "
                   "complexidade e carater da internacao."),
        granularidade="municipio x mes x perfil x complexidade x carater",
        colunas=[
            Coluna("cod_municipio_6", "codigo IBGE do municipio de atendimento"),
            Coluna("uf", "sigla da unidade federativa", ("estado",)),
            Coluna("ano", "ano da internacao"),
            Coluna("mes", "mes da internacao"),
            Coluna("competencia", "ano e mes no formato AAAAMM"),
            Coluna("perfil_atendimento",
                   "capitulo CID-10 do diagnostico principal",
                   ("perfil", "tipo de atendimento", "doenca", "especialidade")),
            Coluna("complexidade", "media ou alta complexidade"),
            Coluna("carater_internacao", "eletivo, urgencia ou acidente",
                   ("carater", "urgencia", "eletiva")),
            Coluna("internacoes", "quantidade de internacoes",
                   ("volume", "atendimentos", "aih")),
            Coluna("dias_permanencia", "total de dias de permanencia",
                   ("leitos-dia",)),
            Coluna("permanencia_media", "media de dias por internacao",
                   ("tempo de internacao", "permanencia")),
            Coluna("transferencias", "internacoes encerradas por transferencia"),
            Coluna("taxa_transferencia", "percentual de transferencias"),
            Coluna("obitos", "quantidade de obitos", ("mortes",)),
            Coluna("taxa_mortalidade", "percentual de obitos", ("mortalidade",)),
            Coluna("valor_total", "valor total pago em reais",
                   ("custo", "gasto", "valor")),
            Coluna("valor_medio_aih", "valor medio por internacao",
                   ("custo medio", "ticket medio")),
            Coluna("idade_media", "idade media dos pacientes"),
        ],
    ),
    "T_SAUDE_IND_CAPACIDADE_MUNICIPAL": Tabela(
        nome="T_SAUDE_IND_CAPACIDADE_MUNICIPAL",
        descricao=("Pressao assistencial por municipio e mes. A taxa de "
                   "ocupacao compara os dias de permanencia consumidos com os "
                   "leitos SUS disponiveis multiplicados pelos dias do mes."),
        granularidade="municipio x mes",
        colunas=[
            Coluna("municipio", "nome do municipio", ("cidade",)),
            Coluna("uf", "sigla da unidade federativa", ("estado",)),
            Coluna("regiao", "regiao geografica"),
            Coluna("competencia", "ano e mes no formato AAAAMM"),
            Coluna("populacao", "populacao estimada pelo IBGE em 2024",
                   ("habitantes",)),
            Coluna("porte", "classificacao do municipio por populacao"),
            Coluna("internacoes", "internacoes no municipio no mes"),
            Coluna("leitos_sus", "leitos disponibilizados ao SUS",
                   ("leitos", "capacidade")),
            Coluna("taxa_ocupacao",
                   "ocupacao dos leitos; acima de 1 a demanda superou a capacidade",
                   ("ocupacao", "lotacao", "pressao")),
            Coluna("situacao",
                   "classificacao: Folga, Adequada, Atencao ou Critica",
                   ("status", "critico", "critica")),
            Coluna("leitos_por_100mil_hab", "leitos SUS por 100 mil habitantes"),
            Coluna("meta_leitos_oms", "leitos esperados pelo parametro da OMS"),
            Coluna("deficit_leitos_oms", "quantos leitos faltam para a meta",
                   ("deficit", "falta de leitos")),
            Coluna("permanencia_media", "media de dias por internacao"),
            Coluna("taxa_transferencia", "percentual de transferencias"),
            Coluna("custo_medio_aih", "valor medio por internacao"),
        ],
    ),
    "T_SAUDE_RANK_HOSPITAIS": Tabela(
        nome="T_SAUDE_RANK_HOSPITAIS",
        descricao=("Estabelecimentos de saude ordenados por volume de "
                   "internacoes SUS, com indicadores de eficiencia."),
        granularidade="estabelecimento (CNES)",
        colunas=[
            Coluna("nome_fantasia", "nome do estabelecimento",
                   ("hospital", "unidade", "estabelecimento")),
            Coluna("uf", "sigla da unidade federativa", ("estado",)),
            Coluna("esfera", "esfera administrativa: municipal, estadual, federal"),
            Coluna("internacoes", "quantidade de internacoes"),
            Coluna("leitos_sus", "leitos disponibilizados ao SUS", ("leitos",)),
            Coluna("permanencia_media", "media de dias por internacao"),
            Coluna("giro_leito_ano", "internacoes por leito no ano",
                   ("giro", "eficiencia", "rotatividade")),
            Coluna("taxa_mortalidade", "percentual de obitos"),
            Coluna("taxa_transferencia",
                   "percentual de pacientes encaminhados a outro estabelecimento",
                   ("transferencia", "encaminhamento", "resolutividade")),
            Coluna("custo_medio_aih", "valor medio por internacao"),
            Coluna("ranking_regional", "posicao no ranking por volume"),
        ],
    ),
    "T_SAUDE_DIM_MUNICIPIO": Tabela(
        nome="T_SAUDE_DIM_MUNICIPIO",
        descricao=("Municipios brasileiros com populacao estimada pelo IBGE, "
                   "regiao, porte e meta de leitos pelo parametro da OMS."),
        granularidade="municipio",
        colunas=[
            Coluna("municipio", "nome do municipio", ("cidade",)),
            Coluna("uf", "sigla da unidade federativa"),
            Coluna("regiao", "regiao geografica"),
            Coluna("populacao", "populacao estimada em 2024", ("habitantes",)),
            Coluna("porte", "classificacao por populacao"),
            Coluna("meta_leitos_oms", "leitos esperados pelo parametro da OMS"),
        ],
    ),
    "T_SAUDE_SERIE_DIARIA_UF": Tabela(
        nome="T_SAUDE_SERIE_DIARIA_UF",
        descricao=("Serie diaria de internacoes por UF pela data real de "
                   "internacao, com dia da semana e marcacao de feriado."),
        granularidade="UF x dia",
        colunas=[
            Coluna("uf", "sigla da unidade federativa"),
            Coluna("data", "data da internacao", ("dia",)),
            Coluna("internacoes", "internacoes no dia"),
            Coluna("dia_semana", "0 = segunda-feira, 6 = domingo"),
            Coluna("feriado", "1 se a data e feriado nacional"),
        ],
    ),
    "T_SAUDE_PREVISAO_INTERNACOES": Tabela(
        nome="T_SAUDE_PREVISAO_INTERNACOES",
        descricao=("Previsao diaria de internacoes por UF pelo modelo de "
                   "perfil semanal com ajuste de feriado."),
        granularidade="UF x dia",
        colunas=[
            Coluna("uf", "sigla da unidade federativa"),
            Coluna("data", "data prevista"),
            Coluna("internacoes_previstas", "internacoes estimadas",
                   ("previsao", "projecao", "estimativa")),
            Coluna("limite_inferior", "limite inferior do intervalo de 95%"),
            Coluna("limite_superior", "limite superior do intervalo de 95%"),
            Coluna("tipo", "historico ou previsao"),
            Coluna("mape_validacao", "erro percentual medio na validacao"),
        ],
    ),
}

# Vocabulario auxiliar reconhecido nas perguntas.
UFS = {
    "es": "ES", "espirito santo": "ES",
    "mg": "MG", "minas": "MG", "minas gerais": "MG",
    "rj": "RJ", "rio de janeiro": "RJ", "rio": "RJ",
    "sp": "SP", "sao paulo": "SP",
}

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def contexto_para_prompt() -> str:
    """Dicionario completo em texto, exibido no painel e usado como contexto."""
    return "\n\n".join(tabela.descreve() for tabela in CATALOGO.values())
