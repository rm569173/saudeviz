"""
Desenha o diagrama de arquitetura do SaudeViz para o slide 10 do PPT.

Usa Pillow em vez de uma ferramenta de diagrama porque o resultado precisa
sair versionado e reproduzivel: se um numero mudar, roda de novo e o PNG e
regerado igual. Um .drawio exportado a mao nao teria essa propriedade.

As cores sao as mesmas de app/tema.py, para o diagrama nao destoar dos prints
do painel que aparecem nos slides seguintes.

Saida: apresentacao/arquitetura_solucao.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app import tema  # noqa: E402

# --- Escala -----------------------------------------------------------------
# Desenha em 2x e reduz no final: e o jeito de conseguir borda e texto suaves
# sem depender de antialiasing nativo, que o Pillow nao faz para retangulo.
E = 2
L, A = 1600 * E, 800 * E

FUNDO = "#ffffff"
CARTAO = "#f7f7f5"
BORDA = tema.GRADE
TEXTO = tema.TEXTO_PRIMARIO
FRACO = tema.TEXTO_SECUNDARIO
SETA = "#9a9994"

AZUL = tema.SERIES[0]
LARANJA = tema.SERIES[1]
AQUA = tema.SERIES[2]
AMARELO = tema.SERIES[3]
VIOLETA = tema.SERIES[6]

FONTES = Path("C:/Windows/Fonts")


def fonte(nome: str, tamanho: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTES / nome), tamanho * E)


F_TITULO = fonte("segoeuib.ttf", 30)
F_SUB = fonte("segoeui.ttf", 15)
F_ETAPA = fonte("segoeuib.ttf", 16)
F_CAIXA = fonte("segoeuib.ttf", 14)
F_CORPO = fonte("segoeui.ttf", 12)
F_NUM = fonte("segoeuib.ttf", 13)
F_PE = fonte("segoeui.ttf", 12)

img = Image.new("RGB", (L, A), FUNDO)
d = ImageDraw.Draw(img)


def px(v: float) -> int:
    return int(round(v * E))


def caixa(x, y, w, h, cor_topo, titulo, linhas, destaque=None, raio=10):
    """Cartao com faixa colorida no topo, titulo e linhas de detalhe."""
    x, y, w, h, raio = px(x), px(y), px(w), px(h), px(raio)
    d.rounded_rectangle([x, y, x + w, y + h], raio, fill=CARTAO,
                        outline=BORDA, width=px(1))
    # Faixa de cor: identifica a etapa sem depender de ler o texto.
    d.rounded_rectangle([x, y, x + w, y + px(5)], px(3), fill=cor_topo)
    d.rectangle([x, y + px(3), x + w, y + px(5)], fill=cor_topo)

    cy = y + px(16)
    d.text((x + px(12), cy), titulo, font=F_CAIXA, fill=TEXTO)
    cy += px(20)
    for linha in linhas:
        d.text((x + px(12), cy), linha, font=F_CORPO, fill=FRACO)
        cy += px(16)
    if destaque:
        d.text((x + px(12), y + h - px(22)), destaque, font=F_NUM,
               fill=cor_topo)


def seta(x1, y1, x2, y2, cor=SETA, espessura=2, ponta=10):
    """
    Seta entre dois pontos, com a ponta orientada pela direção da linha.

    Ponta fixa na horizontal ficaria torta nas setas diagonais que saem das
    quatro fontes para o Bronze.
    """
    import math

    x1, y1, x2, y2 = px(x1), px(y1), px(x2), px(y2)
    p, e = px(ponta), px(espessura)
    ang = math.atan2(y2 - y1, x2 - x1)
    # Recua a linha para ela não aparecer por dentro da ponta.
    bx, by = x2 - p * math.cos(ang), y2 - p * math.sin(ang)
    d.line([x1, y1, bx, by], fill=cor, width=e)

    larg = p * 0.5
    d.polygon([
        (x2, y2),
        (bx - larg * math.sin(ang), by + larg * math.cos(ang)),
        (bx + larg * math.sin(ang), by - larg * math.cos(ang)),
    ], fill=cor)


def etapa(x, y, numero, texto, cor):
    """Rotulo numerado acima de cada coluna."""
    cx, cy, r = px(x), px(y), px(12)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor)
    caixa_n = d.textbbox((0, 0), numero, font=F_NUM)
    d.text((cx - (caixa_n[2] - caixa_n[0]) / 2,
            cy - (caixa_n[3] - caixa_n[1]) / 2 - px(2)),
           numero, font=F_NUM, fill="#ffffff")
    d.text((cx + px(18), cy - px(9)), texto, font=F_ETAPA, fill=TEXTO)


# --- Cabecalho --------------------------------------------------------------
d.text((px(60), px(46)), "SaúdeViz — arquitetura da solução",
       font=F_TITULO, fill=TEXTO)
d.text((px(60), px(88)),
       "Quatro fontes públicas · pipeline Medallion no Databricks · "
       "camada de consumo no Oracle · painel público",
       font=F_SUB, fill=FRACO)
d.line([px(60), px(120), px(L / E - 60), px(120)], fill=BORDA, width=px(1))

# --- Colunas ----------------------------------------------------------------
# Quatro colunas iguais ocupando a largura util, com 60 px de respiro entre
# elas para as setas.
COL = [60, 430, 800, 1170]
LARG = 310
TOPO = 200

etapa(COL[0] + 12, 160, "1", "Fontes públicas", AZUL)
etapa(COL[1] + 12, 160, "2", "Databricks", LARANJA)
etapa(COL[2] + 12, 160, "3", "Oracle 19c", AQUA)
etapa(COL[3] + 12, 160, "4", "Consumo", VIOLETA)

# 1 - Fontes
fontes = [
    ("SIH/SUS", ["FTP DATASUS · .dbc · 60 arquivos"], "7.015.106 registros"),
    ("CNES", ["API REST · JSON",
              "estabelecimentos e leitos"], "4.481 + 18.644"),
    ("IBGE", ["CSV · população municipal"], "5.571 municípios"),
    ("Open-Meteo", ["API REST · clima diário das capitais"], "366 dias × 4"),
]
y = TOPO
centro_fonte = []
for titulo, linhas, num in fontes:
    altura = 46 + 16 * len(linhas) + 18
    caixa(COL[0], y, LARG, altura, AZUL, titulo, linhas, num)
    centro_fonte.append(y + altura / 2)
    y += altura + 16

# 2 - Medallion
camadas = [
    ("Bronze", ["Delta · dado cru preservado"], "4 tabelas"),
    ("Prata", ["limpeza, tipagem, decodificação"], "6.934.245 registros"),
    ("Ouro", ["star schema + indicadores"], "5.546.817 internações em 2024"),
]
y = TOPO
centro_camada = {}
for titulo, linhas, num in camadas:
    caixa(COL[1], y, LARG, 96, LARANJA, titulo, linhas, num)
    centro_camada[titulo] = y + 48
    if titulo != "Ouro":
        # Seta vertical entre as camadas.
        cx = px(COL[1] + LARG / 2)
        d.line([cx, px(y + 96), cx, px(y + 108)], fill=SETA, width=px(2))
        d.polygon([(cx, px(y + 114)),
                   (cx - px(5), px(y + 108)), (cx + px(5), px(y + 108))],
                  fill=SETA)
    y += 110

caixa(COL[1], y + 14, LARG, 74, LARANJA, "Free Edition",
      ["serverless · Unity Catalog", "landing zone de 218 MB"])

# 3 - Oracle
caixa(COL[2], TOPO, LARG, 152, AQUA, "Tabelas T_SAUDE_*",
      ["fatos, dimensões e indicadores",
       "COMMENT ON em linguagem de",
       "negócio em cada coluna"], "11 tabelas")
caixa(COL[2], TOPO + 166, LARG, 118, AQUA, "Carga",
      ["python-oracledb em modo thin",
       "lotes de 10.000 linhas"], "6.401 linhas/s")
caixa(COL[2], TOPO + 298, LARG, 118, AQUA, "Integridade",
      ["três conferências partindo de",
       "tabelas independentes"], "fecham no mesmo total")

# 4 - Consumo
caixa(COL[3], TOPO, LARG, 152, VIOLETA, "Painel Streamlit",
      ["Visão geral · Capacidade · Perfis",
       "Previsão · Pergunte em português",
       "saudeviz.streamlit.app"])
caixa(COL[3], TOPO + 166, LARG, 118, VIOLETA, "Tradutor NL→SQL",
      ["11 intenções sobre os COMMENT ON",
       "SQL gerado visível na tela"])
caixa(COL[3], TOPO + 298, LARG, 118, VIOLETA, "Contingência",
      ["DuckDB sobre parquet, se o",
       "banco não responder em 8s"])

# --- Setas entre colunas ----------------------------------------------------
# As quatro fontes convergem para o Bronze: e ali que todo dado cru aterrissa.
for cy in centro_fonte:
    seta(COL[0] + LARG + 10, cy, COL[1] - 10, centro_camada["Bronze"])

# Do Ouro sai o dado modelado para o Oracle.
seta(COL[1] + LARG + 10, centro_camada["Ouro"], COL[2] - 10, TOPO + 76)
seta(COL[2] + LARG + 10, TOPO + 76, COL[3] - 10, TOPO + 76)

# --- Rodape -----------------------------------------------------------------
ry = 640
d.line([px(60), px(ry), px(L / E - 60), px(ry)], fill=BORDA, width=px(1))
d.text((px(60), px(ry + 20)),
       "Recorte: ES · MG · RJ · SP — 89 milhões de habitantes. "
       "O pipeline é parametrizado por UF.",
       font=F_PE, fill=FRACO)
d.text((px(60), px(ry + 42)),
       "Dimensão temporal pela data de internação, não pela competência de "
       "pagamento do SIH — que arrasta 42% dos registros de meses anteriores.",
       font=F_PE, fill=FRACO)
d.text((px(60), px(ry + 64)),
       "Select AI nativo indisponível no Oracle 19c Enterprise da FIAP; "
       "substituído pelo tradutor determinístico sobre os mesmos metadados.",
       font=F_PE, fill=FRACO)
d.text((px(60), px(ry + 96)),
       "Challenge FIAP × Oracle 2026 · Sprint 2 · "
       "Lucas Ventura Araujo Ribas Colen — RM 569173 — 1TSCOA",
       font=F_PE, fill=FRACO)

# --- Grava ------------------------------------------------------------------
destino = RAIZ / "apresentação" / "arquitetura_solucao.png"
destino.parent.mkdir(parents=True, exist_ok=True)
img.resize((L // E, A // E), Image.LANCZOS).save(destino, "PNG", optimize=True)
print(f"gravado: {destino}")
print(f"{(L // E)}x{(A // E)} px · {destino.stat().st_size / 1024:.0f} KB")
