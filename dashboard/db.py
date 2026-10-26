"""Conexão com o Supabase e leitura das tabelas da camada diamond (geradas pelo dbt)."""

import os
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        if not SUPABASE_DB_URL:
            raise RuntimeError("SUPABASE_DB_URL não configurada (defina em .env ou nas env vars do Render).")
        _engine = create_engine(SUPABASE_DB_URL, pool_pre_ping=True)
    return _engine


TABELAS_DIAMOND_PERMITIDAS = {
    "diamond_por_idade",
    "diamond_por_escolaridade",
    "diamond_por_localidade",
    "diamond_serie_temporal",
    "diamond_resumo_geral",
}


@lru_cache(maxsize=32)
def carregar_tabela(nome_tabela: str) -> pd.DataFrame:
    if nome_tabela not in TABELAS_DIAMOND_PERMITIDAS:
        raise ValueError(f"Tabela não permitida: {nome_tabela}")
    query = f"select * from diamond.{nome_tabela}"
    return pd.read_sql(query, get_engine())


def listar_anos() -> list:
    df = carregar_tabela("diamond_resumo_geral")
    return sorted(df["ano_censo"].unique().tolist())


def listar_ufs() -> list:
    df = carregar_tabela("diamond_por_localidade")
    return sorted(df["uf"].dropna().unique().tolist())
