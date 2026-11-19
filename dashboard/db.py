"""Leitura das tabelas da camada diamond a partir de um arquivo DuckDB local.

O arquivo (dados/censo.duckdb) é gerado pelo ETL + dbt-duckdb e vai junto com o
app — não há servidor de banco para pausar, expirar ou configurar.
"""

import os
import threading
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

DUCKDB_PATH = Path(os.environ.get("DUCKDB_PATH", Path(__file__).resolve().parent / "dados" / "censo.duckdb"))

TABELAS_DIAMOND_PERMITIDAS = {
    "diamond_por_idade",
    "diamond_por_escolaridade",
    "diamond_por_localidade",
    "diamond_serie_temporal",
    "diamond_resumo_geral",
}

_conexao = None
_trava = threading.Lock()


def _conectar() -> duckdb.DuckDBPyConnection:
    """Conexão somente leitura e sem acesso a arquivos/rede (sandbox para o SQL gerado pela IA)."""
    global _conexao
    if _conexao is None:
        if not DUCKDB_PATH.exists():
            raise FileNotFoundError(
                f"Arquivo {DUCKDB_PATH} não encontrado. Rode o ETL (etl/04_load_gold_to_duckdb.py) e o dbt."
            )
        _conexao = duckdb.connect(
            str(DUCKDB_PATH),
            read_only=True,
            config={"enable_external_access": False, "lock_configuration": True},
        )
    return _conexao


def consultar(sql: str, max_linhas: int = 500) -> pd.DataFrame:
    """Executa um SELECT e devolve no máximo `max_linhas` linhas."""
    with _trava:  # uma conexão compartilhada; cursor por consulta
        cursor = _conectar().cursor()
    try:
        return cursor.execute(f"select * from ({sql}) as consulta limit {int(max_linhas)}").df()
    finally:
        cursor.close()


@lru_cache(maxsize=32)
def carregar_tabela(nome_tabela: str) -> pd.DataFrame:
    if nome_tabela not in TABELAS_DIAMOND_PERMITIDAS:
        raise ValueError(f"Tabela não permitida: {nome_tabela}")
    with _trava:
        cursor = _conectar().cursor()
    try:
        return cursor.execute(f"select * from diamond.{nome_tabela}").df()
    finally:
        cursor.close()


def diagnostico() -> dict:
    """Usado pela rota /saude."""
    info = {"arquivo": str(DUCKDB_PATH), "existe": DUCKDB_PATH.exists()}
    try:
        info["tamanho_mb"] = round(DUCKDB_PATH.stat().st_size / 1e6, 2)
        info["anos"] = listar_anos()
        info["linhas"] = {t: len(carregar_tabela(t)) for t in sorted(TABELAS_DIAMOND_PERMITIDAS)}
        info["status"] = "ok"
    except Exception as erro:
        info["status"] = "erro"
        info["erro"] = repr(erro)[:1000]
    return info


def listar_anos() -> list:
    return sorted(int(a) for a in carregar_tabela("diamond_resumo_geral")["ano_censo"].unique())


def listar_ufs() -> list:
    return sorted(carregar_tabela("diamond_por_localidade")["uf"].dropna().unique().tolist())
