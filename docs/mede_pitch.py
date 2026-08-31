"""
Cronometra o roteiro do pitch pela contagem de palavras faladas.

Cinco minutos e limite rigido do enunciado. Estimar "no olho" quanto tempo um
texto leva falado nao funciona: a primeira versao deste roteiro parecia curta
e tinha 5min58s. Aqui o numero sai medido.

Conta so o que esta em bloco de citacao (o que voce fala), ignorando titulo,
instrucao de tela e checklist.

Uso: py docs/mede_pitch.py
"""
import pathlib, re, unicodedata

RITMO = 150.0  # palavras por minuto, fala clara em portugues

texto = pathlib.Path("docs/roteiro_pitch.md").read_text(encoding="utf-8")
linhas = texto.splitlines()

blocos, atual = [], None
for l in linhas:
    m = re.match(r"^#{2,3} (.+?) — (\d+)(?:min)?(\d*)s?", l)
    if l.startswith("## ") or l.startswith("### "):
        titulo = l.lstrip("# ").strip()
        # tempo declarado no titulo
        mm = re.search(r"(?:(\d+)min)?(\d+)s", titulo)
        alvo = (int(mm.group(1) or 0) * 60 + int(mm.group(2))) if mm else None
        atual = {"titulo": titulo, "alvo": alvo, "palavras": 0}
        blocos.append(atual)
    elif l.startswith("> ") and atual and atual["alvo"]:
        fala = l[2:].strip()
        if fala.startswith("**"):
            continue
        atual["palavras"] += len(re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9,.%-]*", fala))

total_p = total_a = 0
print(f"{'BLOCO':46} {'palavras':>8} {'real':>7} {'alvo':>6}")
print("-" * 72)
for b in blocos:
    if not b["alvo"]:
        continue
    seg = b["palavras"] / RITMO * 60
    total_p += b["palavras"]
    total_a += b["alvo"]
    marca = "" if seg <= b["alvo"] + 3 else "  <-- estourou"
    print(f"{''.join(c for c in b['titulo'] if ord(c) < 256)[:46]:46} {b['palavras']:>8} {seg:>6.0f}s {b['alvo']:>5}s{marca}")
print("-" * 72)
seg = total_p / RITMO * 60
print(f"{'TOTAL':46} {total_p:>8} {seg:>6.0f}s {total_a:>5}s")
print(f"\n{int(seg)//60}min{int(seg)%60:02d}s de fala · limite 5min00s")
print(f"margem: {300 - seg:.0f}s para pausas de navegacao")


# ---------------------------------------------------------------------------
# Teleprompter
# ---------------------------------------------------------------------------

def gera_teleprompter():
    """
    Versao limpa para ler enquanto grava.

    Sai do mesmo arquivo do roteiro: editar o roteiro e rodar isto mantem os
    dois iguais. Duas copias mantidas a mao divergem sempre.
    """
    saida = ["SAUDEVIZ - ROTEIRO DO PITCH",
             "Lucas Ventura Araujo Ribas Colen - RM 569173 - 1TSCOA",
             "",
             "Limite: 5 minutos. Fala medida: 4min39s.",
             "[colchetes] = instrucao, nao leia em voz alta",
             "=" * 66, ""]

    bloco_atual = None
    for l in linhas:
        if l.startswith("#"):
            titulo = l.lstrip("# ").strip()
            if re.search(r"\d+s", titulo):
                bloco_atual = titulo
                saida += ["", "=" * 66, titulo.upper(), "=" * 66, ""]
            else:
                bloco_atual = None
        elif l.startswith("*") and l.endswith("*") and bloco_atual:
            saida.append(f"[{l.strip('*').strip()}]")
            saida.append("")
        elif l.startswith("> ") and bloco_atual:
            fala = l[2:].strip()
            if fala.startswith("**") or not fala:
                continue
            saida.append(fala.strip('"'))
        elif l.startswith(">") and bloco_atual and len(l.strip()) == 1:
            saida.append("")

    destino = pathlib.Path("docs/teleprompter.txt")
    destino.write_text("\n".join(saida) + "\n", encoding="utf-8")
    print(f"\nteleprompter gravado: {destino} "
          f"({len(saida)} linhas)")


gera_teleprompter()
