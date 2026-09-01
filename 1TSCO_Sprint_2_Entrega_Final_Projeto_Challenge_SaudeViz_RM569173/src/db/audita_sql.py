"""
Procura, em todo o projeto, o padrao de SQL que quebra no Oracle:

    SUM(x) AS x           no SELECT
    ORDER BY SUM(x)       depois

No ORDER BY o Oracle resolve o alias antes da coluna de origem. Como o alias
ja e o proprio agregado, repetir a funcao cria um agregado aninhado e o banco
rejeita. O DuckDB aceita, entao o erro so aparece em producao.
"""
import pathlib
import re
import sys

RAIZ = pathlib.Path(sys.argv[1])
AGREGADOS = ("SUM", "COUNT", "AVG", "MIN", "MAX")

problemas = []
suspeitas = []

for caminho in sorted(RAIZ.rglob("*.py")) + sorted(RAIZ.rglob("*.sql")):
    if "__pycache__" in str(caminho) or ".git" in str(caminho):
        continue
    texto = caminho.read_text(encoding="utf-8", errors="replace")

    # Aliases que repetem o nome da coluna agregada
    aliases_arriscados = set()
    for func in AGREGADOS:
        for m in re.finditer(rf"{func}\(\s*(\w+)\s*\)\s+AS\s+(\w+)",
                             texto, re.IGNORECASE):
            coluna, alias = m.group(1), m.group(2)
            if coluna.lower() == alias.lower():
                aliases_arriscados.add(alias.lower())

    for numero, linha in enumerate(texto.splitlines(), 1):
        if not re.search(r"ORDER\s+BY", linha, re.IGNORECASE):
            continue
        for func in AGREGADOS:
            m = re.search(rf"ORDER\s+BY\s+{func}\(\s*(\w+)\s*\)",
                          linha, re.IGNORECASE)
            if m:
                coluna = m.group(1).lower()
                registro = (str(caminho.relative_to(RAIZ)), numero, linha.strip())
                if coluna in aliases_arriscados:
                    problemas.append(registro)
                else:
                    suspeitas.append(registro)

print("=" * 78)
print("QUEBRA NO ORACLE - agregado no ORDER BY sobre alias de mesmo nome")
print("=" * 78)
for arquivo, numero, linha in problemas:
    print(f"  {arquivo}:{numero}")
    print(f"      {linha}")
if not problemas:
    print("  nenhum")

print()
print("=" * 78)
print("AGREGADO NO ORDER BY sem conflito de alias - valido, so para conferencia")
print("=" * 78)
for arquivo, numero, linha in suspeitas:
    print(f"  {arquivo}:{numero}")
    print(f"      {linha}")
if not suspeitas:
    print("  nenhum")

sys.exit(1 if problemas else 0)
