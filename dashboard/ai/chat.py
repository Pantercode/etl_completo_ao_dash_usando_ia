"""Chat de perguntas em linguagem natural sobre os dados (text-to-SQL no DuckDB).

Segurança em camadas:
1. o Gemini só conhece o schema das tabelas `diamond_*`;
2. a query é validada (um único SELECT/WITH, só tabelas diamond permitidas);
3. a conexão DuckDB é somente leitura e sem acesso a arquivos/rede (ver db.py),
   então mesmo um SQL malicioso não consegue escrever nem ler nada fora do banco.
"""

import re

import pandas as pd

import db
from ai.gemini_client import IAIndisponivel, perguntar

SCHEMA_DESCRICAO = """
Banco DuckDB, schema "diamond", Censo Escolar da Educação Básica (INEP). Cada linha já é um agregado.

diamond.diamond_resumo_geral(ano_censo INT, total_matriculas BIGINT, total_rede_publica BIGINT,
    total_rede_privada BIGINT, total_urbana BIGINT, total_rural BIGINT, qtd_ufs INT, qtd_municipios INT)
    -- 1 linha por ano: totais do Brasil. Use para perguntas nacionais simples.
diamond.diamond_serie_temporal(ano_censo INT, uf TEXT, rede TEXT, qtd_matriculas BIGINT)
    -- total de matrículas por ano x UF x rede.
diamond.diamond_por_localidade(ano_censo INT, uf TEXT, co_municipio TEXT, municipio TEXT,
    localizacao TEXT, rede TEXT, qtd_matriculas BIGINT)
    -- por município e zona de residência do aluno. Única tabela com município.
diamond.diamond_por_idade(ano_censo INT, uf TEXT, rede TEXT, faixa_etaria TEXT, qtd_matriculas BIGINT)
diamond.diamond_por_escolaridade(ano_censo INT, uf TEXT, rede TEXT, etapa_ensino TEXT, qtd_matriculas BIGINT)

Valores exatos (respeite acentos e maiúsculas):
- uf: siglas como 'SP', 'BA', 'AM'.
- rede: 'Pública' | 'Privada'.
- localizacao: 'Urbana' | 'Rural' | 'Não informado'.
- faixa_etaria: '0-3' | '4-5' | '6-10' | '11-14' | '15-17' | '18+'.
- etapa_ensino: 'Educação Infantil' | 'Ensino Fundamental' | 'Ensino Médio' | 'Educação Profissional' | 'EJA' | 'Educação Especial'.
- Anos disponíveis: {anos}.
"""

PROMPT_SQL = """Converta a pergunta em UMA query SQL para DuckDB, somente leitura (SELECT ou WITH ... SELECT),
usando APENAS as tabelas abaixo.
{schema}
Recorte ativo no painel do usuário: {recorte}

Regras:
- Sempre agregue com SUM(qtd_matriculas) e GROUP BY; nunca some colunas de tabelas diferentes na mesma linha.
- Se a pergunta não disser o ano, filtre ano_censo = {ano_padrao}.
- Se a pergunta não disser estado/rede e o recorte ativo tiver um, aplique o recorte ativo.
- Para rankings: ORDER BY desc e LIMIT (padrão 10). Para participação use
  ROUND(100.0 * parte / total, 1) AS pct_<nome>.
- Nomes de colunas de saída curtos e em português (ex.: uf, matriculas, pct_rural).
- Se a pergunta pedir para alterar/apagar dados ou não puder ser respondida com estas tabelas
  (ex.: notas, professores, escolas, região), responda exatamente: SELECT 'fora_do_escopo' AS status
- Responda só com o SQL, sem explicação, sem markdown, sem ponto-e-vírgula.

Exemplos:
P: Quais os 5 municípios com mais matrículas?
SQL: SELECT municipio, uf, SUM(qtd_matriculas) AS matriculas FROM diamond.diamond_por_localidade WHERE ano_censo = {ano_padrao} GROUP BY municipio, uf ORDER BY matriculas DESC LIMIT 5
P: Qual UF tem a maior proporção de alunos na zona rural?
SQL: SELECT uf, ROUND(100.0 * SUM(qtd_matriculas) FILTER (WHERE localizacao = 'Rural') / SUM(qtd_matriculas), 1) AS pct_rural FROM diamond.diamond_por_localidade WHERE ano_censo = {ano_padrao} GROUP BY uf ORDER BY pct_rural DESC LIMIT 10

P: {pergunta}
SQL:"""

PROMPT_CORRECAO = """A query abaixo falhou no DuckDB. Corrija-a seguindo as mesmas regras e responda só com o SQL.
Pergunta: {pergunta}
Query: {sql}
Erro: {erro}
{schema}
SQL corrigido:"""

PROMPT_RESPOSTA = """Você é analista de dados do Censo Escolar. Responda à pergunta usando SOMENTE o resultado abaixo.

Pergunta: {pergunta}
Recorte considerado: {recorte}
Resultado (CSV, {n_linhas} linhas):
{csv}

Regras:
- Comece pela resposta direta, com o número principal em **negrito**. Ex.: "**São Paulo**, com **9,8 mi** de matrículas."
- Números no padrão brasileiro (9,8 mi; 1.234; 12,5%). Não invente números que não estão no resultado.
- No máximo 2 frases. Se houver ranking, cite os 3 primeiros.
- Sem rodeios: proibido "com base nos dados", "de acordo com a tabela", "parece", "aproximadamente".
- Se o resultado não responde exatamente à pergunta, diga em 1 frase o que ele mostra e o que faltou.
"""

_PALAVRAS_PROIBIDAS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|call|copy|attach|detach|install|load|"
    r"pragma|set|export|import|checkpoint|vacuum)\b|read_\w+\s*\(|glob\s*\(",
    re.IGNORECASE,
)


def _extrair_sql(texto: str) -> str:
    texto = re.sub(r"```(?:sql)?", "", texto, flags=re.IGNORECASE).strip()
    texto = re.sub(r"^\s*SQL:\s*", "", texto, flags=re.IGNORECASE)
    return texto.strip().rstrip(";").strip()


def _validar_sql(sql: str) -> None:
    if not re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("a IA não gerou uma consulta SELECT")
    if ";" in sql:
        raise ValueError("consulta com múltiplos comandos")
    if _PALAVRAS_PROIBIDAS.search(sql):
        raise ValueError("consulta contém operação não permitida")
    ctes = {c.lower() for c in re.findall(r"(?:\bwith|,)\s*(\w+)\s+as\s*\(", sql, flags=re.IGNORECASE)}
    for alvo in re.findall(r"\b(?:from|join)\s+([\w\.\"]+)", sql, flags=re.IGNORECASE):
        nome = alvo.replace('"', "").lower()
        if nome in ctes:
            continue
        esquema, _, tabela = nome.rpartition(".")
        if esquema != "diamond" or tabela not in db.TABELAS_DIAMOND_PERMITIDAS:
            raise ValueError(f"tabela não permitida: {alvo}")


def _inteiros(df: pd.DataFrame) -> pd.DataFrame:
    """SUM no DuckDB vira float no pandas (3570144.0): devolve como inteiro quando não há casas decimais."""
    df = df.copy()
    for coluna in df.select_dtypes("float").columns:
        valores = df[coluna].dropna()
        if len(valores) and (valores % 1 == 0).all():
            df[coluna] = df[coluna].astype("Int64")
    return df


def _gerar_e_executar(pergunta: str, schema: str, recorte: str, ano_padrao) -> tuple[str, pd.DataFrame]:
    sql = _extrair_sql(
        perguntar(PROMPT_SQL.format(schema=schema, recorte=recorte, ano_padrao=ano_padrao, pergunta=pergunta), temperatura=0)
    )
    try:
        _validar_sql(sql)
        return sql, db.consultar(sql)
    except Exception as erro:  # uma tentativa de autocorreção com a mensagem de erro
        sql = _extrair_sql(
            perguntar(PROMPT_CORRECAO.format(pergunta=pergunta, sql=sql, erro=str(erro)[:400], schema=schema), temperatura=0)
        )
        _validar_sql(sql)
        return sql, db.consultar(sql)


def responder(pergunta: str, ano=None, uf=None, rede=None) -> tuple[str, pd.DataFrame | None, str | None]:
    """Retorna (texto_markdown, dataframe_ou_none, sql_ou_none)."""
    anos = db.listar_anos()
    ano_padrao = ano or max(anos)
    partes = [f"ano {ano_padrao}"]
    partes.append(f"UF {uf}" if uf and uf != "TODAS" else "Brasil inteiro")
    partes.append(f"rede {rede}" if rede and rede != "TODAS" else "todas as redes")
    recorte = ", ".join(partes)
    schema = SCHEMA_DESCRICAO.format(anos=", ".join(map(str, anos)))

    try:
        sql, df = _gerar_e_executar(pergunta, schema, recorte, ano_padrao)
    except IAIndisponivel:
        return "A IA está indisponível agora. Tente de novo em alguns segundos.", None, None
    except Exception as erro:
        return (
            f"Não consegui montar uma consulta válida para essa pergunta ({erro}). "
            "Tente citar o que quer medir (matrículas, % rural, % pública) e o recorte (UF, etapa, faixa etária).",
            None,
            None,
        )

    if "fora_do_escopo" in sql:
        return (
            "Essa pergunta está fora do que o painel cobre. Dá para perguntar sobre **matrículas** por ano, estado, "
            "município, rede (pública/privada), zona (urbana/rural), etapa de ensino e faixa etária.",
            None,
            None,
        )
    if df.empty:
        return "Nenhum registro atende a essa pergunta no recorte considerado.", df, sql

    df = _inteiros(df)
    try:
        texto = perguntar(
            PROMPT_RESPOSTA.format(
                pergunta=pergunta, recorte=recorte, n_linhas=len(df), csv=df.head(25).to_csv(index=False)
            ),
            temperatura=0.1,
        )
    except IAIndisponivel:
        texto = "Resultado da consulta abaixo (a IA não conseguiu redigir o resumo agora)."
    return texto, df, sql
