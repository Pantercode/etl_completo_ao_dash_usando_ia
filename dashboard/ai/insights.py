"""Gera um resumo em texto (2-3 frases) para os dados já filtrados de um gráfico.

Cacheado por (titulo, assinatura_dos_dados) para não gastar cota do Gemini a
cada re-render do mesmo filtro.
"""

from functools import lru_cache

import pandas as pd

from ai.gemini_client import perguntar

PROMPT_TEMPLATE = """Você é um analista de dados educacionais brasileiros.
Resuma em português, em no máximo 3 frases curtas e diretas, a tendência ou
destaque mais importante nos dados agregados abaixo sobre o Censo Escolar.
Não invente números que não estejam na tabela. Não repita a tabela, só o
insight.

Contexto do gráfico: {titulo}

Dados (CSV):
{dados_csv}
"""


@lru_cache(maxsize=256)
def _gerar_insight_cacheado(titulo: str, dados_csv: str) -> str:
    prompt = PROMPT_TEMPLATE.format(titulo=titulo, dados_csv=dados_csv)
    return perguntar(prompt)


def gerar_insight(df: pd.DataFrame, titulo: str, max_linhas: int = 30) -> str:
    if df.empty:
        return "Sem dados para os filtros selecionados."
    amostra = df.head(max_linhas)
    dados_csv = amostra.to_csv(index=False)
    return _gerar_insight_cacheado(titulo, dados_csv)
