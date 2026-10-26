"""Harmonização de nomes de coluna do Censo Escolar entre os anos 2019-2023.

Validado contra o arquivo real de 2023 (microdados_ed_basica_2023.csv): a
estrutura é um único arquivo por ano, em nível de ESCOLA, com contagens de
matrícula pré-agregadas em colunas QT_MAT_* (por etapa, faixa etária, sexo,
raça e zona urbana/rural). Essas colunas QT_MAT_*/QT_DOC_*/QT_TUR_* são
nomes "oficiais" e estáveis do INEP — não houve necessidade de mapear
nenhuma delas para 2023.

Antes de rodar para 2019-2022, confira rapidamente se os mesmos nomes
existem no cabeçalho de cada ano (`head -1 microdados_ed_basica_{ano}.csv`).
Se algum ano usar um nome diferente, adicione aqui — é o único lugar que
precisa mudar.

Estrutura: {nome_canonico: {ano: nome_real_na_coluna_daquele_ano}}
Se um ano não aparece no dict interno, assume-se que o nome canônico é
igual ao nome real naquele ano (sem mudança).
"""

COLUNAS_ESCOLA = {
    "co_escola": {},  # CO_ENTIDADE
    "uf": {},  # SG_UF
    "co_municipio": {},  # CO_MUNICIPIO
    "municipio": {},  # NO_MUNICIPIO
    "localizacao": {},  # TP_LOCALIZACAO (1=Urbana, 2=Rural) — localização da escola
    "dependencia_administrativa": {},  # TP_DEPENDENCIA (1=Federal,2=Estadual,3=Municipal,4=Privada)
}

NOMES_REAIS_DEFAULT = {
    "co_escola": "CO_ENTIDADE",
    "uf": "SG_UF",
    "co_municipio": "CO_MUNICIPIO",
    "municipio": "NO_MUNICIPIO",
    "localizacao": "TP_LOCALIZACAO",
    "dependencia_administrativa": "TP_DEPENDENCIA",
}


def coluna_real(nome_canonico: str, ano: int, mapeamento: dict = COLUNAS_ESCOLA) -> str:
    """Resolve o nome real da coluna para um ano específico."""
    overrides = mapeamento.get(nome_canonico, {})
    return overrides.get(ano, NOMES_REAIS_DEFAULT[nome_canonico])
