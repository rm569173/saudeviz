"""
Envio da camada Bronze para um Volume do Unity Catalog no Databricks.

O Databricks Free Edition roda apenas compute serverless e nao expoe o DBFS
raiz para escrita: os arquivos ficam em Volumes do Unity Catalog, no caminho
/Volumes/<catalogo>/<schema>/<volume>/...

Autenticacao
------------
Nenhuma credencial e lida deste arquivo nem gravada em disco pelo projeto.
Defina as duas variaveis de ambiente na SUA sessao de terminal antes de rodar:

    PowerShell:
        $env:DATABRICKS_HOST  = "https://dbc-ec79b4c9-62ce.cloud.databricks.com"
        $env:DATABRICKS_TOKEN = "<cole aqui o seu Personal Access Token>"

O token e gerado em: Settings > User > Developer > Access tokens > Generate.

Uso
---
    py -m src.db.databricks_upload --testar
    py -m src.db.databricks_upload
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

CATALOGO = os.getenv("DATABRICKS_CATALOGO", "workspace")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "saudeviz")
VOLUME = os.getenv("DATABRICKS_VOLUME", "landing")

RAIZ_VOLUME = f"/Volumes/{CATALOGO}/{SCHEMA}/{VOLUME}"


def _cliente():
    """Cria o cliente do workspace a partir das variaveis de ambiente."""
    from databricks.sdk import WorkspaceClient

    if not os.getenv("DATABRICKS_HOST") or not os.getenv("DATABRICKS_TOKEN"):
        raise SystemExit(
            "Defina DATABRICKS_HOST e DATABRICKS_TOKEN no terminal antes de "
            "rodar. Veja as instrucoes no topo deste arquivo.")
    return WorkspaceClient()


def testa_conexao() -> None:
    """
    Diagnostico da conexao, endpoint a endpoint.

    Tokens com escopo restrito falham em endpoints especificos em vez de
    falharem por completo, entao cada capacidade e testada isoladamente:
    assim da para ver se o problema e o token, a rede ou o escopo.
    """
    token = os.getenv("DATABRICKS_TOKEN", "")
    host = os.getenv("DATABRICKS_HOST", "")

    print("=" * 62)
    print("CREDENCIAL (o token nunca e exibido)")
    print("=" * 62)
    print(f"  Host                 : {host or '(vazio)'}")
    print(f"  Token: comprimento   : {len(token)} caracteres")
    print(f"  Token: prefixo dapi  : {token.startswith('dapi')}")
    if len(token) < 20:
        print("\n  >> O token esta curto demais. Um PAT do Databricks tem")
        print("     por volta de 40 caracteres e comeca com 'dapi'.")
        print("     A colagem provavelmente nao funcionou. Refaca o passo")
        print("     definindo a variavel diretamente:")
        print('       $env:DATABRICKS_TOKEN = "cole-o-token-aqui"')
        return

    cliente = _cliente()

    testes = [
        ("IAM - identificar usuario", lambda: cliente.current_user.me().user_name),
        ("Unity Catalog - catalogos",
         lambda: ", ".join(c.name for c in cliente.catalogs.list()) or "(nenhum)"),
        ("Unity Catalog - schemas",
         lambda: ", ".join(s.name for s in
                           cliente.schemas.list(catalog_name=CATALOGO)) or "(nenhum)"),
        # A Files API exige o caminho completo /Volumes/<cat>/<schema>/<vol>;
        # listar apenas "/Volumes" devolve "Path is missing a catalog name".
        # Por isso a capacidade de Volumes e testada pela API do Unity Catalog.
        ("Unity Catalog - volumes",
         lambda: ", ".join(
             v.name for v in cliente.volumes.list(catalog_name=CATALOGO,
                                                  schema_name="default")) or "(nenhum)"),
    ]

    print()
    print("=" * 62)
    print("CAPACIDADES DO TOKEN")
    print("=" * 62)
    for nome, chamada in testes:
        try:
            print(f"  [OK]    {nome:<34} {chamada()}")
        except Exception as erro:
            resumo = str(erro).strip().splitlines()[0][:70]
            print(f"  [FALHA] {nome:<34} {resumo}")

    print()
    print("Se apenas o IAM falhar, o token funciona: e so escopo de identidade.")
    print("Se tudo falhar, o token ou o host estao errados.")


def prepara_destino() -> None:
    """Cria o schema e o volume de landing, se ainda nao existirem."""
    cliente = _cliente()

    schemas = {s.name for s in cliente.schemas.list(catalog_name=CATALOGO)}
    if SCHEMA not in schemas:
        cliente.schemas.create(name=SCHEMA, catalog_name=CATALOGO,
                               comment="SaudeViz - Challenge FIAP x Oracle 2026")
        log.info("Schema criado: %s.%s", CATALOGO, SCHEMA)

    volumes = {v.name for v in cliente.volumes.list(catalog_name=CATALOGO,
                                                    schema_name=SCHEMA)}
    if VOLUME not in volumes:
        from databricks.sdk.service.catalog import VolumeType

        cliente.volumes.create(catalog_name=CATALOGO, schema_name=SCHEMA,
                               name=VOLUME, volume_type=VolumeType.MANAGED,
                               comment="Arquivos brutos enviados da estacao local")
        log.info("Volume criado: %s", RAIZ_VOLUME)


def _envia(cliente, origem: Path, destino: str) -> int:
    """Envia um arquivo para o Volume, sobrescrevendo o que existir."""
    with origem.open("rb") as arquivo:
        cliente.files.upload(destino, arquivo, overwrite=True)
    return origem.stat().st_size


def envia_bronze() -> None:
    """
    Envia os parquets da camada Bronze e os arquivos auxiliares.

    Mantem o particionamento por UF: o Spark reconhece a estrutura de
    diretorios e consegue podar particoes na leitura.
    """
    cliente = _cliente()
    prepara_destino()

    arquivos: list[tuple[Path, str]] = []

    for parquet in sorted((config.BRONZE / "sih").rglob("*.parquet")):
        uf = parquet.parent.name
        arquivos.append((parquet, f"{RAIZ_VOLUME}/sih/{uf}/{parquet.name}"))

    for nome in ("estabelecimentos.parquet", "leitos.parquet"):
        origem = config.BRONZE / "cnes" / nome
        if origem.exists():
            arquivos.append((origem, f"{RAIZ_VOLUME}/cnes/{nome}"))

    origem = config.BRONZE / "ibge" / "municipios.parquet"
    if origem.exists():
        arquivos.append((origem, f"{RAIZ_VOLUME}/ibge/municipios.parquet"))

    if config.CSV_POPULACAO.exists():
        arquivos.append((config.CSV_POPULACAO,
                         f"{RAIZ_VOLUME}/ibge/{config.CSV_POPULACAO.name}"))

    total_bytes = sum(o.stat().st_size for o, _ in arquivos)
    log.info("Enviando %s arquivos (%.1f MB) para %s",
             len(arquivos), total_bytes / 1e6, RAIZ_VOLUME)

    enviados = 0
    inicio = time.time()
    for posicao, (origem, destino) in enumerate(arquivos, start=1):
        enviados += _envia(cliente, origem, destino)
        if posicao % 10 == 0 or posicao == len(arquivos):
            decorrido = time.time() - inicio
            log.info("  %s/%s arquivos | %.1f de %.1f MB | %.0f s",
                     posicao, len(arquivos), enviados / 1e6,
                     total_bytes / 1e6, decorrido)

    log.info("Upload concluido em %.0f s", time.time() - inicio)


def baixa_ouro(destino: Path | None = None) -> None:
    """
    Traz de volta a camada Ouro processada no Databricks.

    O painel Streamlit precisa de um retrato local para continuar de pe se o
    banco da faculdade estiver indisponivel numa apresentacao.

    Atencao ao formato: o Spark grava um DIRETORIO por tabela, contendo
    part-00000-....snappy.parquet e _SUCCESS - e nao um arquivo unico. Como o
    03_ouro usa coalesce(1), ha exatamente um part por tabela, que baixamos e
    renomeamos para <tabela>.parquet.
    """
    cliente = _cliente()
    destino = destino or config.OURO
    destino.mkdir(parents=True, exist_ok=True)

    origem = f"{RAIZ_VOLUME}/ouro"
    try:
        entradas = list(cliente.files.list_directory_contents(origem))
    except Exception as erro:
        raise SystemExit(
            f"Nao foi possivel listar {origem}: {erro}\n"
            "Rode antes o notebook 03_ouro no Databricks, que e quem exporta "
            "a camada Ouro para o Volume.") from erro

    if not entradas:
        raise SystemExit(f"{origem} esta vazio. Rode o notebook 03_ouro.")

    baixados = 0
    for entrada in entradas:
        tabela = entrada.path.rstrip("/").rsplit("/", 1)[-1]

        if entrada.is_directory:
            partes = [
                item for item in cliente.files.list_directory_contents(entrada.path)
                if item.path.endswith(".parquet")
            ]
            if not partes:
                log.warning("Sem arquivo parquet em %s", entrada.path)
                continue
            if len(partes) > 1:
                log.warning("%s tem %s partes; o 03_ouro deveria usar "
                            "coalesce(1). Baixando apenas a primeira.",
                            tabela, len(partes))
            caminho_remoto = partes[0].path
            nome_local = f"{tabela}.parquet"
        elif entrada.path.endswith(".parquet"):
            caminho_remoto = entrada.path
            nome_local = tabela
        else:
            continue

        resposta = cliente.files.download(caminho_remoto)
        alvo = destino / nome_local
        with alvo.open("wb") as arquivo:
            arquivo.write(resposta.contents.read())
        baixados += 1
        log.info("Baixado %-34s %.2f MB", nome_local, alvo.stat().st_size / 1e6)

    if not baixados:
        raise SystemExit(
            "Nenhum parquet encontrado. Confira se o notebook 03_ouro "
            "concluiu a celula de exportacao.")
    log.info("Camada Ouro local: %s tabelas em %s", baixados, destino)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Transferencia com o Databricks")
    parser.add_argument("--testar", action="store_true",
                        help="apenas testa a conexao e lista os catalogos")
    parser.add_argument("--baixar-ouro", action="store_true",
                        help="traz a camada ouro do Databricks para o disco local")
    args = parser.parse_args()

    if args.testar:
        testa_conexao()
    elif args.baixar_ouro:
        baixa_ouro()
    else:
        envia_bronze()
