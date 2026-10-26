"""Chat de perguntas em linguagem natural sobre os dados (text-to-SQL).

Restrito de propósito: o Gemini só vê o schema das tabelas `diamond_*` (não o
banco inteiro) e a query gerada é validada como um único SELECT somente
leitura antes de ser executada.
"""

import re

import pandas as pd

from ai.gemini_client import perguntar
from db import TABELAS_DIAMOND_PERMITIDAS, get_engine

SCHEMA_DESCRICAO = """
Tabelas disponíveis no schema "diamond" (Postgres), todas sobre o Censo Escolar (INEP) 2019-2023:

diamond.diamond_por_idade(ano_censo int, uf text, rede text, faixa_etaria text, qtd_matriculas bigint)
diamond.diamond_por_escolaridade(ano_censo int, uf text, rede text, etapa_ensino text, qtd_matriculas bigint)
diamond.diamond_por_localidade(ano_censo int, uf text, co_municipio text, municipio text, localizacao text, rede text, qtd_matriculas bigint)
diamond.diamond_serie_temporal(ano_censo int, uf text, rede text, qtd_matriculas bigint)
diamond.diamond_resumo_geral(ano_censo int, total_matriculas bigint, total_rede_publica bigint, total_rede_privada bigint, total_urbana bigint, total_rural bigint, qtd_ufs int, qtd_municipios int)

Valores possíveis: localizacao em ('Urbana','Rural','Não informado'); rede em ('Pública','Privada','Não informado').
"""

PROMPT_TEMPLATE = """Você converte perguntas em português sobre o Censo Escolar em UMA única
query SQL (Postgres), somente leitura (SELECT), usando APENAS as tabelas abaixo.
Responda só com a query SQL, sem explicação, sem markdown, sem ponto-e-vírgula no final.

{schema}

Pergunta: {pergunta}

SQL:
"""

_PALAVRAS_PROIBIDAS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|call|copy)\b", re.IGNORECASE
)


def _extrair_sql(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```sql\s*|^```\s*|```$", "", texto, flags=re.IGNORECASE | re.MULTILINE).strip()
    return texto.rstrip(";").strip()


def _validar_sql(sql: str) -> None:
    if not sql.lower().startswith("select"):
        raise ValueError("A IA não gerou uma consulta SELECT.")
    if ";" in sql:
        raise ValueError("Consulta com múltiplos comandos não é permitida.")
    if _PALAVRAS_PROIBIDAS.search(sql):
        raise ValueError("Consulta contém operação não permitida.")
    tabelas_citadas = re.findall(r"diamond\.(\w+)", sql, flags=re.IGNORECASE)
    for tabela in tabelas_citadas:
        if tabela.lower() not in TABELAS_DIAMOND_PERMITIDAS:
            raise ValueError(f"Tabela não permitida: {tabela}")


def responder(pergunta: str) -> tuple[str, pd.DataFrame | None]:
    """Retorna (texto_resposta, dataframe_ou_none)."""
    bruto = perguntar(PROMPT_TEMPLATE.format(schema=SCHEMA_DESCRICAO, pergunta=pergunta))
    sql = _extrair_sql(bruto)

    try:
        _validar_sql(sql)
    except ValueError as exc:
        return f"Não consegui montar uma consulta segura para essa pergunta ({exc}).", None

    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            try:
                df = pd.read_sql(sql, conn)
            finally:
                trans.rollback()  # somente leitura: nunca commitamos, mesmo sendo SELECT
    except Exception as exc:
        return f"Erro ao consultar os dados: {exc}", None

    if df.empty:
        return "Não encontrei dados para essa pergunta.", df

    resumo_prompt = (
        "Responda em português, em 1-2 frases, a pergunta do usuário com base "
        f"nesta tabela de resultado (CSV):\n{df.head(20).to_csv(index=False)}\n\n"
        f"Pergunta original: {pergunta}"
    )
    texto = perguntar(resumo_prompt)
    return texto, df
