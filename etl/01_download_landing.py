"""Landing: baixa e extrai os microdados do Censo Escolar (INEP) para data/landing/{ano}/.

Uso:
    python etl/01_download_landing.py
"""

import zipfile
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # usa o cert store do Windows: necessário para confiar na cadeia ICP-Brasil de *.gov.br

import requests

import config


def baixar_ano(ano: int) -> Path:
    destino_dir = config.LANDING_DIR / str(ano)
    zip_path = destino_dir / f"microdados_censo_escolar_{ano}.zip"

    if destino_dir.exists() and any(destino_dir.rglob("*.csv")):
        print(f"[{ano}] já extraído em {destino_dir}, pulando download.")
        return destino_dir

    destino_dir.mkdir(parents=True, exist_ok=True)
    url = config.URL_PATTERN.format(ano=ano)
    print(f"[{ano}] baixando {url} ...")

    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        baixado = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                baixado += len(chunk)
                if total:
                    pct = 100 * baixado / total
                    print(f"\r[{ano}] {pct:5.1f}%", end="")
        print()

    print(f"[{ano}] extraindo zip...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(destino_dir)

    zip_path.unlink()
    print(f"[{ano}] OK -> {destino_dir}")
    return destino_dir


def main():
    for ano in config.ANOS:
        baixar_ano(ano)


if __name__ == "__main__":
    main()
