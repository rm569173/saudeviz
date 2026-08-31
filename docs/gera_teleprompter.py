"""
Teleprompter da apresentacao em sala, slide a slide.

Le docs/slides.json (o manifesto de titulos que gera_ppt.py grava) e o modulo
notas_apresentador. Nao abre o .pptx de proposito: o arquivo fica travado
enquanto estiver aberto no PowerPoint, e e justamente nessa hora que voce
quer regerar o teleprompter.

Traz o tempo de cada slide e o acumulado, para voce saber onde esta do
orcamento no meio da apresentacao.

Nao confundir com docs/teleprompter_video.txt, que e o pitch de 5 minutos:
o video vende o resultado, isto mostra o caminho.

Uso: py docs/gera_teleprompter.py
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from notas_apresentador import NOTAS  # noqa: E402

MANIFESTO = AQUI / "slides.json"
SAIDA = AQUI / "teleprompter_apresentacao.txt"

RITMO = 150.0   # palavras por minuto, fala clara em portugues
LARGURA = 74    # linha mais larga que isso cansa de acompanhar


def main() -> None:
    if not MANIFESTO.exists():
        raise SystemExit("rode antes: py docs/gera_ppt.py")
    titulos = {int(k): v for k, v in
               json.loads(MANIFESTO.read_text(encoding="utf-8")).items()}

    total_slides = max(titulos)
    linhas = [
        "SAUDEVIZ - TELEPROMPTER DA APRESENTACAO",
        "Lucas Ventura Araujo Ribas Colen - RM 569173 - 1TSCOA",
        "",
        f"{total_slides} slides. [colchetes] = instrucao, nao leia em voz alta.",
        "Para o video de 5 minutos, use teleprompter_video.txt.",
        "",
    ]

    acumulado = 0.0
    resumo = []
    for numero in range(1, total_slides + 1):
        titulo = titulos.get(numero, "(sem titulo)")
        nota = " ".join((NOTAS.get(numero) or "").split())
        segundos = len(nota.split()) / RITMO * 60
        acumulado += segundos
        resumo.append((numero, titulo, segundos, acumulado))

        linhas += [
            "=" * LARGURA,
            f"SLIDE {numero:>2}/{total_slides}   ·   {segundos:.0f}s   ·   "
            f"acumulado {int(acumulado) // 60}:{int(acumulado) % 60:02d}",
            titulo.upper(),
            "=" * LARGURA,
            "",
        ]
        if not nota:
            linhas += ["[sem nota]", ""]
            continue
        # Quebra em frases curtas: paragrafo longo no teleprompter faz perder
        # a linha ao levantar os olhos para a plateia.
        for trecho in NOTAS[numero].split(chr(10) * 2):
            trecho = " ".join(trecho.split())
            if trecho:
                linhas += textwrap.wrap(trecho, LARGURA) + [""]

    indice = ["", "=" * LARGURA, "INDICE E ORCAMENTO DE TEMPO",
              "=" * LARGURA, ""]
    for numero, titulo, seg, acum in resumo:
        indice.append(f"{numero:>2}. {titulo[:42]:42} {seg:>4.0f}s   "
                      f"{int(acum) // 60:>2}:{int(acum) % 60:02d}")
    indice += [
        "",
        f"TOTAL: {int(acumulado) // 60} min {int(acumulado) % 60:02d}s de "
        f"fala, a {RITMO:.0f} palavras por minuto.",
        "",
        "Sem contar pausa, troca de slide e pergunta da banca.",
        "Reserve mais uns 20% para isso.",
    ]

    quebra = chr(10)
    SAIDA.write_text(quebra.join(linhas + indice) + quebra, encoding="utf-8")
    print(f"gravado: {SAIDA.name}")
    print(f"{total_slides} slides · {int(acumulado) // 60} min "
          f"{int(acumulado) % 60:02d}s de fala")
    print(quebra + "slides mais longos:")
    for numero, titulo, seg, _ in sorted(resumo, key=lambda r: -r[2])[:5]:
        print(f"   {numero:>2}. {titulo[:40]:40} {seg:>4.0f}s")


if __name__ == "__main__":
    main()
