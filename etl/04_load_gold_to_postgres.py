"""Carrega o parquet gold (já agregado e pequeno) para o schema `staging` no Supabase.

Uso:
    python etl/04_load_gold_to_postgres.py
"""

import pandas as pd
from sqlalchemy import create_engine, text

import config

TABELA_DESTINO = "matriculas_agregadas"


def main():
    if not config.SUPABASE_DB_URL:
        raise RuntimeError(
            "SUPABASE_DB_URL não configurada. Copie .env.example para .env e preencha a connection string do Supabase."
        )

    caminho_gold = config.GOLD_DIR / "matriculas_agregadas"
    if not caminho_gold.exists():
        raise RuntimeError(f"{caminho_gold} não existe. Rode 03_bronze_to_gold.py antes.")

    df = pd.read_parquet(caminho_gold)
    print(f"Lido {len(df):,} linhas do gold parquet.")

    engine = create_engine(config.SUPABASE_DB_URL)

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.STAGING_SCHEMA}"))

    df.to_sql(
        TABELA_DESTINO,
        engine,
        schema=config.STAGING_SCHEMA,
        if_exists="replace",
        index=False,
        chunksize=5000,
        method="multi",
    )
    print(f"Carregado em {config.STAGING_SCHEMA}.{TABELA_DESTINO} ({len(df):,} linhas).")


if __name__ == "__main__":
    main()
