"""
Tradutor de linguagem natural para SQL — o papel do Select AI no SaudeViz.

O Select AI so existe no Autonomous Database, e a instancia da FIAP e uma
19c Enterprise sem DBMS_CLOUD_AI (conferido no all_objects). Este modulo faz
o equivalente sobre os mesmos metadados: os COMMENT ON das tabelas
T_SAUDE_*, catalogados em metadados.py.

E deterministico: classifica a intencao por vocabulario, extrai entidades e
monta o SQL a partir de modelos parametrizados. O SQL e real, executado no
banco e exibido na tela, como o "SELECT AI showsql".

Nao e um modelo de linguagem. Fora do repertorio mapeado ele diz que nao
entendeu, em vez de inventar um numero.
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.selectai.metadados import MESES, UFS, normaliza

log = logging.getLogger(__name__)


@dataclass
class Entidades:
    """Parametros extraidos da pergunta em linguagem natural."""
    uf: str | None = None
    municipio: str | None = None
    mes: int | None = None
    limite: int = 10
    situacao: str | None = None


@dataclass
class Traducao:
    """Resultado da traducao: SQL pronto e o raciocinio que levou ate ele."""
    intencao: str
    pergunta: str
    sql: str
    explicacao: str
    entidades: Entidades
    confianca: float
    tabelas: tuple[str, ...] = ()
    alternativas: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extracao de entidades
# ---------------------------------------------------------------------------

def extrai_entidades(pergunta: str) -> Entidades:
    """Identifica UF, mes, quantidade e situacao mencionados na pergunta."""
    texto = normaliza(pergunta)
    entidades = Entidades()

    # UF: verifica as expressoes mais longas primeiro, para "rio de janeiro"
    # nao ser capturado pelo "rio" e "sao paulo" nao virar apenas "sp".
    for expressao in sorted(UFS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(expressao)}\b", texto):
            entidades.uf = UFS[expressao]
            break

    # Nomes de estado saem do texto antes da busca por mes: "Rio de Janeiro"
    # contem "janeiro" e daria a toda pergunta sobre o RJ um filtro de janeiro
    # que ninguem pediu.
    texto_meses = texto
    for expressao in sorted(UFS, key=len, reverse=True):
        texto_meses = re.sub(f"(?<![a-z]){re.escape(expressao)}(?![a-z])",
                             " ", texto_meses)

    # O limite de palavra tambem importa: sem ele "maio" casa dentro de
    # "maior", e "quais hospitais tem maior permanencia" ganha um mes.
    for nome, numero in MESES.items():
        if re.search(f"(?<![a-z]){nome}(?![a-z])", texto_meses):
            entidades.mes = numero
            break

    # "top 5", "os 20 maiores", "10 primeiros"
    quantidade = re.search(r"\b(?:top|primeiros?|maiores|melhores)\s+(\d{1,3})\b", texto)
    if not quantidade:
        quantidade = re.search(r"\b(\d{1,3})\s+(?:maiores|primeiros?|piores|melhores)\b", texto)
    if quantidade:
        entidades.limite = max(1, min(int(quantidade.group(1)), 100))

    if "critic" in texto:
        entidades.situacao = "Critica"
    elif "atencao" in texto:
        entidades.situacao = "Atencao"

    return entidades


def _filtro_uf(entidades: Entidades, alias: str = "") -> str:
    prefixo = f"{alias}." if alias else ""
    return f"AND {prefixo}uf = '{entidades.uf}'" if entidades.uf else ""


def _filtro_mes(entidades: Entidades, alias: str = "") -> str:
    prefixo = f"{alias}." if alias else ""
    if entidades.mes is None:
        return ""
    return f"AND {prefixo}competencia = '2024{entidades.mes:02d}'"


def _limite(n: int, dialeto: str) -> str:
    """O Oracle usa FETCH FIRST; o DuckDB usa LIMIT."""
    return f"LIMIT {n}" if dialeto == "duckdb" else f"FETCH FIRST {n} ROWS ONLY"


# ---------------------------------------------------------------------------
# Intencoes reconhecidas
#
# Cada intencao tem: palavras que a identificam, uma funcao que monta o SQL e
# uma explicacao em linguagem de negocio do que a consulta faz.
# ---------------------------------------------------------------------------

def _sql_municipios_criticos(e: Entidades, d: str) -> tuple[str, str]:
    situacao = e.situacao or "Critica"
    sql = f"""
SELECT municipio,
       uf,
       competencia,
       populacao,
       internacoes,
       leitos_sus,
       taxa_ocupacao,
       situacao
  FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
 WHERE situacao = '{situacao}'
   {_filtro_uf(e)}
   {_filtro_mes(e)}
 ORDER BY taxa_ocupacao DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        f"Lista os municipios classificados como '{situacao}' pelo indicador de "
        "pressao assistencial, ordenados pela taxa de ocupacao. Ocupacao acima "
        "de 1,0 significa que a demanda superou a capacidade de leitos SUS "
        "declarada — um alerta para investigar, nao prova de colapso.")
    return sql, explicacao


def _sql_crescimento_municipios(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
WITH semestres AS (
    SELECT municipio,
           uf,
           populacao,
           SUM(CASE WHEN mes <= 6 THEN internacoes ELSE 0 END) AS primeiro_semestre,
           SUM(CASE WHEN mes >  6 THEN internacoes ELSE 0 END) AS segundo_semestre
      FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
     WHERE 1 = 1
       {_filtro_uf(e)}
     GROUP BY municipio, uf, populacao
)
SELECT municipio,
       uf,
       populacao,
       primeiro_semestre,
       segundo_semestre,
       ROUND(100.0 * (segundo_semestre - primeiro_semestre)
             / primeiro_semestre, 1) AS crescimento_pct
  FROM semestres
 WHERE primeiro_semestre >= 500
 ORDER BY crescimento_pct DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        "Compara o segundo semestre contra o primeiro por municipio. O filtro "
        "de 500 internacoes no primeiro semestre evita que uma cidade que saiu "
        "de 2 para 6 internacoes apareca liderando com '200% de crescimento'.")
    return sql, explicacao


def _sql_perfis_pressao(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT perfil_atendimento,
       SUM(internacoes)                                        AS internacoes,
       SUM(dias_permanencia)                                   AS leitos_dia,
       ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)      AS permanencia_media,
       ROUND(SUM(valor_total) / SUM(internacoes), 2)           AS custo_medio_aih
  FROM T_SAUDE_FATO_INTERNACAO_MENSAL
 WHERE 1 = 1
   {_filtro_uf(e)}
   {_filtro_mes(e)}
 GROUP BY perfil_atendimento
 ORDER BY leitos_dia DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        "Ordena os perfis de atendimento (capitulos CID-10) pelo total de "
        "leitos-dia consumidos, e nao pelo numero de internacoes. Volume alto "
        "com permanencia curta pressiona menos que volume baixo com permanencia "
        "longa — e essa diferenca e invisivel num painel que so conta atendimentos.")
    return sql, explicacao


def _sql_ranking_hospitais(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT nome_fantasia,
       uf,
       esfera,
       internacoes,
       leitos_sus,
       permanencia_media,
       giro_leito_ano,
       taxa_transferencia,
       custo_medio_aih
  FROM T_SAUDE_RANK_HOSPITAIS
 WHERE 1 = 1
   {_filtro_uf(e)}
 ORDER BY internacoes DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        "Ranking de estabelecimentos por volume de internacoes SUS. O giro de "
        "leito (internacoes por leito no ano) separa eficiencia de tamanho: "
        "dois hospitais com os mesmos leitos e giros diferentes tem perfis "
        "assistenciais distintos.")
    return sql, explicacao


def _sql_permanencia_hospitais(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT nome_fantasia,
       uf,
       internacoes,
       leitos_sus,
       permanencia_media,
       taxa_mortalidade
  FROM T_SAUDE_RANK_HOSPITAIS
 WHERE internacoes >= 1000
   {_filtro_uf(e)}
 ORDER BY permanencia_media DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        "Estabelecimentos com maior permanencia media, entre os que tem ao "
        "menos mil internacoes no ano. O corte de volume evita que unidades "
        "pequenas com poucos casos longos distorcam o ranking.")
    return sql, explicacao


def _sql_transferencias(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT nome_fantasia,
       uf,
       esfera,
       internacoes,
       leitos_sus,
       taxa_transferencia,
       permanencia_media
  FROM T_SAUDE_RANK_HOSPITAIS
 WHERE internacoes >= 1000
   {_filtro_uf(e)}
 ORDER BY taxa_transferencia DESC
 {_limite(e.limite, d)}
""".strip()
    explicacao = (
        "Estabelecimentos que mais encaminham pacientes a outra unidade. A taxa "
        "de transferencia mede resolutividade: nao e 'ha muitas internacoes "
        "aqui', e 'pacientes estao saindo daqui porque nao ha como trata-los "
        "aqui'.")
    return sql, explicacao


def _sql_leitos_deficit(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT uf,
       COUNT(DISTINCT municipio)               AS municipios,
       SUM(deficit_leitos_oms)                 AS deficit_leitos,
       ROUND(AVG(leitos_por_100mil_hab), 1)    AS leitos_por_100mil_hab,
       300                                     AS meta_oms_por_100mil
  FROM (SELECT DISTINCT municipio, uf, deficit_leitos_oms, leitos_por_100mil_hab
          FROM T_SAUDE_IND_CAPACIDADE_MUNICIPAL
         WHERE 1 = 1 {_filtro_uf(e)}) t
 GROUP BY uf
 ORDER BY leitos_por_100mil_hab ASC
""".strip()
    explicacao = (
        "Compara a oferta de leitos SUS com o parametro da OMS de 300 leitos "
        "por 100 mil habitantes. A subconsulta usa DISTINCT por municipio "
        "porque o indicador e mensal: somar as doze competencias contaria o "
        "mesmo leito doze vezes.")
    return sql, explicacao


def _sql_volume_por_uf(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT uf,
       SUM(internacoes)                                     AS internacoes,
       ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)   AS permanencia_media,
       ROUND(100.0 * SUM(obitos) / SUM(internacoes), 2)     AS taxa_mortalidade,
       ROUND(SUM(valor_total) / 1000000, 1)                 AS valor_milhoes
  FROM T_SAUDE_FATO_INTERNACAO_MENSAL
 WHERE 1 = 1
   {_filtro_uf(e)}
   {_filtro_mes(e)}
 GROUP BY uf
 ORDER BY internacoes DESC
""".strip()
    explicacao = ("Volume e indicadores agregados por unidade federativa.")
    return sql, explicacao


def _sql_evolucao_mensal(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT competencia,
       SUM(internacoes)                                     AS internacoes,
       ROUND(SUM(dias_permanencia) / SUM(internacoes), 2)   AS permanencia_media,
       ROUND(SUM(valor_total) / 1000000, 1)                 AS valor_milhoes
  FROM T_SAUDE_FATO_INTERNACAO_MENSAL
 WHERE 1 = 1
   {_filtro_uf(e)}
 GROUP BY competencia
 ORDER BY competencia
""".strip()
    explicacao = (
        "Evolucao mes a mes pela DATA DE INTERNACAO. Importante: nao e a "
        "competencia de pagamento do SIH, que arrasta cerca de 42% de registros "
        "de meses anteriores e distorceria qualquer serie temporal.")
    return sql, explicacao


def _sql_previsao(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT uf,
       competencia,
       SUM(internacoes_previstas)  AS internacoes_previstas,
       SUM(limite_inferior)        AS limite_inferior,
       SUM(limite_superior)        AS limite_superior,
       MAX(mape_validacao)         AS erro_medio_validacao_pct
  FROM T_SAUDE_PREVISAO_INTERNACOES
 WHERE tipo = 'previsao'
   {_filtro_uf(e)}
 GROUP BY uf, competencia
 ORDER BY uf, competencia
""".strip()
    explicacao = (
        "Projecao de internacoes agregada por mes, com intervalo de confianca "
        "de 95%. O modelo e um perfil semanal com ajuste de feriado, validado "
        "em janela expansivel — erro medio em torno de 5,5%.")
    return sql, explicacao


def _sql_dia_semana(e: Entidades, d: str) -> tuple[str, str]:
    sql = f"""
SELECT dia_semana,
       CASE dia_semana
            WHEN 0 THEN 'Segunda' WHEN 1 THEN 'Terca'  WHEN 2 THEN 'Quarta'
            WHEN 3 THEN 'Quinta'  WHEN 4 THEN 'Sexta'  WHEN 5 THEN 'Sabado'
            ELSE 'Domingo' END                          AS dia,
       ROUND(AVG(internacoes), 0)                       AS media_internacoes,
       COUNT(*)                                         AS dias_observados
  FROM T_SAUDE_SERIE_DIARIA_UF
 WHERE feriado = 0
   {_filtro_uf(e)}
 GROUP BY dia_semana
 ORDER BY dia_semana
""".strip()
    explicacao = (
        "Media de internacoes por dia da semana, excluindo feriados. A queda de "
        "fim de semana nao e falta de doente: e a rede eletiva parada. Mede "
        "quanto da operacao e programavel, e portanto remanejavel.")
    return sql, explicacao


# Vocabulario de cada intencao. Sao radicais, nao palavras inteiras:
# "transfer" pega transferencia, transferem e transferido. O peso faz termo
# especifico valer mais que generico.
INTENCOES = {
    "municipios_criticos": {
        "palavras": (("critic", 3), ("ultrapassad", 3), ("acima da capacidade", 3),
                     ("ocupacao", 2), ("lotad", 2), ("colapso", 3),
                     ("sobrecarga", 2), ("estourou", 2), ("no limite", 2)),
        "funcao": _sql_municipios_criticos,
        "titulo": "Municipios em situacao critica de capacidade",
        "tabelas": ("T_SAUDE_IND_CAPACIDADE_MUNICIPAL",),
    },
    "crescimento": {
        "palavras": (("crescimento", 3), ("cresce", 3), ("crescendo", 3),
                     ("aument", 3), ("subiu", 2), ("variacao", 2),
                     ("maior alta", 3), ("expansao", 2)),
        "funcao": _sql_crescimento_municipios,
        "titulo": "Municipios com maior crescimento de internacoes",
        "tabelas": ("T_SAUDE_IND_CAPACIDADE_MUNICIPAL",),
    },
    "perfis": {
        "palavras": (("perfil", 3), ("perfis", 3), ("tipo de atendimento", 3),
                     ("doenca", 2), ("diagnostic", 2), ("especialidade", 2),
                     ("pression", 2), ("capitulo", 2)),
        "funcao": _sql_perfis_pressao,
        "titulo": "Perfis de atendimento que mais pressionam o sistema",
        "tabelas": ("T_SAUDE_FATO_INTERNACAO_MENSAL",),
    },
    "transferencias": {
        "palavras": (("transfer", 4), ("encaminh", 3), ("resolutividade", 3),
                     ("mandar para outro", 3)),
        "funcao": _sql_transferencias,
        "titulo": "Estabelecimentos que mais transferem pacientes",
        "tabelas": ("T_SAUDE_RANK_HOSPITAIS",),
    },
    "permanencia": {
        "palavras": (("permanenc", 4), ("tempo de internacao", 3),
                     ("dias de internacao", 3), ("internacao mais longa", 3),
                     ("demora", 2), ("ficam mais tempo", 3)),
        "funcao": _sql_permanencia_hospitais,
        "titulo": "Estabelecimentos com maior permanencia media",
        "tabelas": ("T_SAUDE_RANK_HOSPITAIS",),
    },
    "hospitais": {
        "palavras": (("hospitais", 1), ("hospital", 1), ("estabelecimento", 1),
                     ("ranking", 1), ("maiores unidades", 2)),
        "funcao": _sql_ranking_hospitais,
        "titulo": "Ranking de hospitais por volume",
        "tabelas": ("T_SAUDE_RANK_HOSPITAIS",),
    },
    "leitos": {
        "palavras": (("leito", 3), ("deficit", 3), ("oms", 3),
                     ("capacidade instalada", 3), ("falta", 2)),
        "funcao": _sql_leitos_deficit,
        "titulo": "Deficit de leitos frente ao parametro da OMS",
        "tabelas": ("T_SAUDE_IND_CAPACIDADE_MUNICIPAL",),
    },
    "previsao": {
        "palavras": (("previsao", 4), ("prever", 4), ("projecao", 3),
                     ("estimativa", 3), ("proximos meses", 3),
                     ("vai ter", 2), ("futuro", 2), ("tendencia", 2)),
        "funcao": _sql_previsao,
        "titulo": "Previsao de internacoes",
        "tabelas": ("T_SAUDE_PREVISAO_INTERNACOES",),
    },
    "dia_semana": {
        "palavras": (("dia da semana", 4), ("fim de semana", 4), ("sabado", 3),
                     ("domingo", 3), ("feriado", 3), ("semanal", 2)),
        "funcao": _sql_dia_semana,
        "titulo": "Internacoes por dia da semana",
        "tabelas": ("T_SAUDE_SERIE_DIARIA_UF",),
    },
    "evolucao": {
        "palavras": (("evolucao", 3), ("mes a mes", 3), ("ao longo do ano", 3),
                     ("sazonalidade", 3), ("por mes", 3), ("mensal", 2),
                     ("serie temporal", 3)),
        "funcao": _sql_evolucao_mensal,
        "titulo": "Evolucao mensal de internacoes",
        "tabelas": ("T_SAUDE_FATO_INTERNACAO_MENSAL",),
    },
    "volume_uf": {
        "palavras": (("quantas internacoes", 3), ("total de internacoes", 3),
                     ("volume", 2), ("por estado", 3), ("por uf", 3),
                     ("comparar estados", 3), ("compare", 2)),
        "funcao": _sql_volume_por_uf,
        "titulo": "Volume de internacoes por UF",
        "tabelas": ("T_SAUDE_FATO_INTERNACAO_MENSAL",),
    },
}


# Perguntas de exemplo do painel. Acentuadas porque sao o que aparece na
# tela; normaliza() tira o acento antes de comparar.
PERGUNTAS_EXEMPLO = [
    "Quais municípios tiveram maior crescimento de internações no último semestre?",
    "Onde a capacidade hospitalar está sendo ultrapassada?",
    "Quais perfis de atendimento mais pressionam o sistema?",
    "Quais hospitais têm maior permanência média em São Paulo?",
    "Quais hospitais mais transferem pacientes?",
    "Quantos leitos faltam em cada estado para atingir a meta da OMS?",
    "Compare o volume de internações por estado",
    "Como as internações variam por dia da semana?",
    "Qual a previsão de internações para os próximos meses em Minas Gerais?",
    "Mostre a evolução mensal de internações no Rio de Janeiro",
]


def traduz(pergunta: str, dialeto: str = "oracle") -> Traducao:
    """
    Traduz a pergunta em SQL.

    A pontuacao de cada intencao e a soma dos termos do seu vocabulario
    presentes no texto, com peso maior para expressoes de varias palavras -
    "dia da semana" e um sinal mais forte que "semana" isolado.
    """
    texto = normaliza(pergunta)
    entidades = extrai_entidades(pergunta)

    pontuacoes: dict[str, float] = {}
    for nome, definicao in INTENCOES.items():
        pontos = 0.0
        for radical, peso in definicao["palavras"]:
            if re.search(r"\b" + re.escape(radical), texto):
                pontos += peso
        if pontos > 0:
            pontuacoes[nome] = pontos

    if not pontuacoes:
        return Traducao(
            intencao="desconhecida",
            pergunta=pergunta,
            sql="",
            explicacao=(
                "Nao consegui mapear essa pergunta para nenhuma consulta do "
                "repertorio. Este tradutor e deterministico: ele reconhece um "
                "conjunto definido de perguntas em vez de tentar adivinhar. "
                "Veja os exemplos ao lado ou reformule usando termos como "
                "internacoes, leitos, ocupacao, transferencia, permanencia ou "
                "previsao."),
            entidades=entidades,
            confianca=0.0,
            alternativas=PERGUNTAS_EXEMPLO[:5],
        )

    melhor = max(pontuacoes, key=pontuacoes.get)
    definicao = INTENCOES[melhor]
    sql, explicacao = definicao["funcao"](entidades, dialeto)

    total = sum(pontuacoes.values())
    confianca = round(pontuacoes[melhor] / total, 2) if total else 0.0

    outras = sorted((p for p in pontuacoes if p != melhor),
                    key=pontuacoes.get, reverse=True)

    return Traducao(
        intencao=definicao["titulo"],
        pergunta=pergunta,
        sql=sql,
        explicacao=explicacao,
        entidades=entidades,
        confianca=confianca,
        tabelas=definicao["tabelas"],
        alternativas=[INTENCOES[o]["titulo"] for o in outras[:3]],
    )


def responde(pergunta: str, motor) -> tuple[Traducao, object]:
    """Traduz e executa, devolvendo a traducao e o resultado da consulta."""
    dialeto = "duckdb" if "duck" in motor.nome.lower() else "oracle"
    traducao = traduz(pergunta, dialeto=dialeto)
    if not traducao.sql:
        return traducao, None
    return traducao, motor.consulta(traducao.sql)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for exemplo in PERGUNTAS_EXEMPLO:
        t = traduz(exemplo)
        print("=" * 74)
        print(f"PERGUNTA : {exemplo}")
        print(f"INTENCAO : {t.intencao}  (confianca {t.confianca:.0%})")
        if t.entidades.uf or t.entidades.mes or t.entidades.limite != 10:
            print(f"ENTIDADES: uf={t.entidades.uf} mes={t.entidades.mes} "
                  f"limite={t.entidades.limite}")
        print(f"SQL      :\n{t.sql}")
