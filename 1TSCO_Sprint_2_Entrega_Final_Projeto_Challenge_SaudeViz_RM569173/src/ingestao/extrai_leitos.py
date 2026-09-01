"""
Complemento da fonte 2 - Leitos hospitalares do CNES (arquivos LT do DATASUS).

A API publica de estabelecimentos nao expoe a quantidade de leitos, que e o
denominador do nosso indicador de pressao assistencial. Os arquivos
LT<UF><AA><MM>.dbc do CNES trazem leitos por estabelecimento e tipo.

Saida: dados/bronze/cnes/leitos.parquet
"""
from __future__ import annotations

import logging
import sys
from ftplib import FTP, error_perm
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src import config
from src.ingestao.extrai_sih import dbc_para_dataframe as _converte

log = logging.getLogger(__name__)

FTP_DIR_LT = "/dissemin/publicos/CNES/200508_/Dados/LT"
DESTINO = config.BRONZE / "cnes"

# Colunas relevantes dos arquivos LT
COLUNAS_LT = [
    "CNES",        # estabelecimento
    "CODUFMUN",    # municipio
    "TP_LEITO",    # tipo de leito
    "CODLEITO",    # especialidade do leito
    "QT_EXIST",    # leitos existentes
    "QT_CONTR",    # leitos contratados
    "QT_SUS",      # leitos disponiveis ao SUS
    "COMPETEN",    # competencia AAAAMM
]


def ingere(ufs=None, ano: int = 2024, mes: int = 12,
           reprocessar: bool = False) -> pd.DataFrame:
    """Baixa os leitos do CNES de uma competencia para todas as UFs."""
    ufs = ufs or config.UFS
    DESTINO.mkdir(parents=True, exist_ok=True)
    alvo = DESTINO / "leitos.parquet"
    if alvo.exists() and not reprocessar:
        log.info("Leitos ja materializados em %s", alvo)
        return pd.read_parquet(alvo)

    ftp = FTP(config.FTP_HOST, timeout=120)
    ftp.login()
    ftp.cwd(FTP_DIR_LT)
    partes = []
    try:
        for uf in ufs:
            arq = f"LT{uf}{str(ano)[2:]}{mes:02d}.dbc"
            destino = config.RAW / "cnes" / arq
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not destino.exists():
                    with open(destino, "wb") as saida:
                        ftp.retrbinary(f"RETR {arq}", saida.write)
            except error_perm:
                log.warning("Leitos indisponiveis para %s %s%02d", uf, ano, mes)
                destino.unlink(missing_ok=True)
                continue
            df = _converte_lt(destino)
            df["UF"] = uf
            partes.append(df)
            destino.unlink(missing_ok=True)
            log.info("Leitos %s -> %s registros", uf, len(df))
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    leitos = pd.concat(partes, ignore_index=True)
    leitos.to_parquet(alvo, index=False)
    log.info("Bronze leitos: %s linhas", len(leitos))
    return leitos


def _converte_lt(caminho: Path) -> pd.DataFrame:
    """Reaproveita o conversor de .dbc do SIH, filtrando as colunas do LT."""
    import shutil
    import tempfile

    from dbfread import DBF
    from pyreaddbc.readdbc import dbc2dbf

    with tempfile.TemporaryDirectory(prefix="saudeviz_lt_") as tmp:
        tmp = Path(tmp)
        dbc_tmp, dbf_tmp = tmp / "e.dbc", tmp / "e.dbf"
        shutil.copyfile(caminho, dbc_tmp)
        dbc2dbf(str(dbc_tmp), str(dbf_tmp))
        df = pd.DataFrame(iter(DBF(str(dbf_tmp), encoding="iso-8859-1",
                                   char_decode_errors="ignore")))
    return df[[c for c in COLUNAS_LT if c in df.columns]]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(ingere().shape)
