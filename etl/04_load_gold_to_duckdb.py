"""Carrega o parquet gold (já agregado e pequeno) no DuckDB, em `staging.matriculas_agregadas`.

O arquivo DuckDB fica em `dashboard/dados/censo.duckdb`: o dbt (dbt-duckdb) cria
as tabelas `diamond.*` nele e o dashboard lê direto dele — sem servidor de banco.

Uso:
    python etl/04_load_gold_to_duckdb.py
"""

import duckdb

import config

TABELA_DESTINO = "matriculas_agregadas"


def main():
    caminho_gold = config.GOLD_DIR / "matriculas_agregadas"
    if not caminho_gold.exists():
        raise RuntimeError(f"{caminho_gold} não existe. Rode 03_bronze_to_gold.py antes.")

    config.DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    padrao = (caminho_gold / "**" / "*.parquet").as_posix()

    with duckdb.connect(str(config.DUCKDB_PATH)) as conn:
        conn.execute(f"create schema if not exists {config.STAGING_SCHEMA}")
        conn.execute(
            f"create or replace table {config.STAGING_SCHEMA}.{TABELA_DESTINO} as "
            "select * from read_parquet(?, hive_partitioning = true)",
            [padrao],
        )
        linhas = conn.execute(f"select count(*) from {config.STAGING_SCHEMA}.{TABELA_DESTINO}").fetchone()[0]

    print(f"Carregado em {config.DUCKDB_PATH} -> {config.STAGING_SCHEMA}.{TABELA_DESTINO} ({linhas:,} linhas).")


if __name__ == "__main__":
    main()
