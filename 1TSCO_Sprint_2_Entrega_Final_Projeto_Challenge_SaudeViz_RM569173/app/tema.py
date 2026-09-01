"""
Paleta e helpers de grafico do painel.

Paleta categorica validada para daltonismo. A ordem dos tons importa: pares
adjacentes mantem separacao sob deuteranopia e protanopia, entao as series
recebem os tons sempre na mesma ordem.

Regras:
  * cor segue a entidade, nunca a posicao no ranking;
  * escala sequencial usa um tom so, do claro ao escuro;
  * cor de status vem sempre com o rotulo, nunca sozinha.
"""
from __future__ import annotations

# Paleta categorica validada - a ordem importa.
SERIES = [
    "#2a78d6",  # 1 azul
    "#eb6834",  # 2 laranja
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 amarelo
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 verde
    "#4a3aa7",  # 7 violeta
    "#e34948",  # 8 vermelho
]

# Cor fixa por UF: a identidade da serie nao muda quando o filtro muda.
COR_UF = {
    "SP": SERIES[0],
    "MG": SERIES[1],
    "RJ": SERIES[2],
    "ES": SERIES[3],
}

# Escala sequencial de tom unico (azul), do claro ao escuro.
SEQUENCIAL_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
                   "#256abf", "#184f95", "#0d366b"]

# Status - nunca reutilizados como cor de serie.
# "Folga" fica em cinza, e nao verde: leito ocioso nao e bom resultado, e
# recurso instalado que a populacao nao esta alcancando.
STATUS = {
    "Folga": "#8a8a84",                        # neutro - ocioso, nao bom
    "Adequada": "#0ca30c",                     # good
    "Atencao": "#fab219",                      # warning
    "Critica": "#d03b3b",                      # critical
    "Sem leito SUS cadastrado": "#c4c3bd",
}

# Icone acompanha a cor de status: cor sozinha nunca carrega significado -
# regra que vale para daltonismo, impressao em preto e branco e modo de alto
# contraste.
ICONE_STATUS = {
    "Folga": "⚪",
    "Adequada": "🟢",
    "Atencao": "🟡",
    "Critica": "🔴",
    "Sem leito SUS cadastrado": "◻️",
}

TEXTO_PRIMARIO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
GRADE = "#e6e5e1"


def layout_base(titulo: str = "", altura: int = 360) -> dict:
    """
    Layout comum a todos os graficos.

    Grade e eixos recessivos, fundo transparente para herdar o tema do
    Streamlit, e rotulos em tom de texto - nunca na cor da serie.
    """
    return {
        "title": {"text": titulo, "font": {"size": 15,
                                           "color": TEXTO_PRIMARIO}},
        "height": altura,
        "margin": {"l": 10, "r": 10, "t": 40 if titulo else 10, "b": 10},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": TEXTO_SECUNDARIO, "size": 12},
        "xaxis": {"gridcolor": GRADE, "zerolinecolor": GRADE,
                  "linecolor": GRADE},
        "yaxis": {"gridcolor": GRADE, "zerolinecolor": GRADE,
                  "linecolor": GRADE},
        "hoverlabel": {"font": {"size": 12}},
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02,
                   "xanchor": "left", "x": 0},
    }


def formata_milhar(valor: float) -> str:
    """1234567 -> '1.234.567' no padrao brasileiro."""
    return f"{valor:,.0f}".replace(",", ".")


def formata_reais(valor: float) -> str:
    """Valor em reais, escalado para a magnitude que couber no cartao."""
    if valor >= 1e9:
        return f"R$ {valor / 1e9:.1f} bi".replace(".", ",")
    if valor >= 1e6:
        return f"R$ {valor / 1e6:.1f} mi".replace(".", ",")
    return f"R$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
