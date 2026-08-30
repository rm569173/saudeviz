"""
Fonte 1 (estruturada) - SIH/SUS via FTP publico do DATASUS.

Os arquivos RD<UF><AA><MM>.dbc contem os microdados de AIH (Autorizacao de
Internacao Hospitalar). O formato .dbc e um DBF comprimido com PKWare DCL,
proprietario do DATASUS; convertemos para .dbf e lemos com dbfread.

Saida: dados/bronze/sih/<UF>/<ANO><MES>.parquet
"""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from ftplib import FTP, error_perm
from pathlib import Path

import pandas as pd
from dbfread import DBF
from pyreaddbc.readdbc import dbc2dbf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config

log = logging.getLogger(__name__)

DESTINO = config.BRONZE / "sih"


def competencias(ano_ini: int, mes_ini: int, ano_fim: int, mes_fim: int):
    """Gera a lista de competencias (ano, mes) do intervalo, inclusivo."""
    ano, mes = ano_ini, mes_ini
    while (ano, mes) <= (ano_fim, mes_fim):
        yield ano, mes
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1


def nome_arquivo(uf: str, ano: int, mes: int) -> str:
    return f"RD{uf}{str(ano)[2:]}{mes:02d}.dbc"


def _abre_ftp() -> FTP:
    ftp = FTP(config.FTP_HOST, timeout=120)
    ftp.login()
    ftp.cwd(config.FTP_DIR_SIH)
    return ftp


def baixa_dbc(ftp: FTP, uf: str, ano: int, mes: int) -> Path | None:
    """Baixa um arquivo .dbc; devolve None se nao existir no servidor."""
    arq = nome_arquivo(uf, ano, mes)
    destino = config.RAW / "sih" / arq
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    try:
        with open(destino, "wb") as saida:
            ftp.retrbinary(f"RETR {arq}", saida.write)
    except error_perm as erro:
        log.warning("Arquivo indisponivel no FTP: %s (%s)", arq, erro)
        destino.unlink(missing_ok=True)
        return None
    return destino


def dbc_para_dataframe(caminho: Path) -> pd.DataFrame:
    """
    Converte .dbc -> .dbf -> DataFrame, mantendo apenas as colunas usadas.

    A conversao roda num diretorio temporario com caminho puramente ASCII:
    a extensao C do dbc2dbf nao aceita caracteres acentuados no path, e o
    repositorio pode estar em uma pasta como "Educacao/Ciencia de Dados".
    """
    with tempfile.TemporaryDirectory(prefix="saudeviz_") as tmp:
        tmp = Path(tmp)
        dbc_tmp = tmp / "entrada.dbc"
        dbf_tmp = tmp / "entrada.dbf"
        shutil.copyfile(caminho, dbc_tmp)
        dbc2dbf(str(dbc_tmp), str(dbf_tmp))
        tabela = DBF(str(dbf_tmp), encoding="iso-8859-1",
                     char_decode_errors="ignore")
        df = pd.DataFrame(iter(tabela))
    presentes = [c for c in config.COLUNAS_SIH if c in df.columns]
    faltantes = set(config.COLUNAS_SIH) - set(presentes)
    if faltantes:
        log.info("Colunas ausentes em %s: %s", caminho.name, sorted(faltantes))
    return df[presentes]


def ingere(ufs=None, ano_ini=None, mes_ini=None, ano_fim=None, mes_fim=None,
           reprocessar: bool = False) -> pd.DataFrame:
    """
    Baixa e converte os arquivos do SIH/SUS para a camada Bronze.

    Devolve um DataFrame com o log de execucao (uf, competencia, linhas).
    """
    ufs = ufs or config.UFS
    ano_ini = ano_ini or config.ANO_INICIO
    mes_ini = mes_ini or config.MES_INICIO
    ano_fim = ano_fim or config.ANO_FIM
    mes_fim = mes_fim or config.MES_FIM

    config.prepara_diretorios()
    registros = []
    ftp = _abre_ftp()
    try:
        for uf in ufs:
            for ano, mes in competencias(ano_ini, mes_ini, ano_fim, mes_fim):
                alvo = DESTINO / uf / f"{ano}{mes:02d}.parquet"
                if alvo.exists() and not reprocessar:
                    registros.append({"uf": uf, "competencia": f"{ano}{mes:02d}",
                                      "linhas": -1, "status": "ja_existia"})
                    continue
                try:
                    dbc = baixa_dbc(ftp, uf, ano, mes)
                except (EOFError, OSError):
                    log.warning("Conexao FTP caiu; reabrindo.")
                    ftp = _abre_ftp()
                    dbc = baixa_dbc(ftp, uf, ano, mes)
                if dbc is None:
                    registros.append({"uf": uf, "competencia": f"{ano}{mes:02d}",
                                      "linhas": 0, "status": "indisponivel"})
                    continue
                df = dbc_para_dataframe(dbc)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(alvo, index=False)
                dbc.unlink(missing_ok=True)  # bronze em parquet substitui o .dbc
                registros.append({"uf": uf, "competencia": f"{ano}{mes:02d}",
                                  "linhas": len(df), "status": "ok"})
                log.info("SIH %s %s%02d -> %s linhas", uf, ano, mes, len(df))
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    return pd.DataFrame(registros)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    resumo = ingere()
    print(resumo.groupby("status")["linhas"].agg(["count", "sum"]))
