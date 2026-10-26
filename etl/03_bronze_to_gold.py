"""Gold: deriva colunas de negócio e AGREGA as contagens de matrícula por município/rede.

Não há join aqui: desde 2019 o INEP já entrega as contagens de matrícula
pré-agregadas por escola nas colunas QT_MAT_* (por etapa, faixa etária, sexo,
raça e zona urbana/rural) — não existe mais um arquivo de matrícula por
aluno. Este passo só seleciona as colunas QT_MAT_* relevantes, deriva
`rede` (a partir de TP_DEPENDENCIA) e agrega (SUM) por
(ano, uf, município, rede), que já reduz ~217 mil linhas (uma por escola)
para algumas dezenas de milhares — pequeno o suficiente para o Supabase.

IMPORTANTE: QT_MAT_ESP (educação especial) pode se sobrepor com as outras
etapas (um aluno de educação especial também é contado na etapa regular que
frequenta) — some os componentes com essa ressalva em mente, não espere que
INF+FUND+MED+PROF+EJA+ESP feche exatamente com QT_MAT_BAS.

Uso:
    python etl/03_bronze_to_gold.py
"""

import config  # precisa vir antes do pyspark

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from schema_mappings.colunas_por_ano import COLUNAS_ESCOLA, coluna_real

# Colunas QT_MAT_* somadas no gold, agrupadas pelo que cada uma representa.
COLS_FAIXA_ETARIA = {
    "0-3": "QT_MAT_BAS_0_3",
    "4-5": "QT_MAT_BAS_4_5",
    "6-10": "QT_MAT_BAS_6_10",
    "11-14": "QT_MAT_BAS_11_14",
    "15-17": "QT_MAT_BAS_15_17",
    "18+": "QT_MAT_BAS_18_MAIS",
}
COLS_ETAPA = {
    "Educação Infantil": "QT_MAT_INF",
    "Ensino Fundamental": "QT_MAT_FUND",
    "Ensino Médio": "QT_MAT_MED",
    "Educação Profissional": "QT_MAT_PROF",
    "EJA": "QT_MAT_EJA",
    "Educação Especial": "QT_MAT_ESP",
}
COLS_LOCALIZACAO_MATRICULA = {
    "Urbana": "QT_MAT_ZR_URB",
    "Rural": "QT_MAT_ZR_RUR",
    "Não informado": "QT_MAT_ZR_NA",
}
COLS_SEXO = {"Feminino": "QT_MAT_BAS_FEM", "Masculino": "QT_MAT_BAS_MASC", "Não declarado": "QT_MAT_BAS_ND"}
COLS_RACA = {
    "Branca": "QT_MAT_BAS_BRANCA",
    "Preta": "QT_MAT_BAS_PRETA",
    "Parda": "QT_MAT_BAS_PARDA",
    "Amarela": "QT_MAT_BAS_AMARELA",
    "Indígena": "QT_MAT_BAS_INDIGENA",
}

TODAS_COLS_QT_MAT = (
    ["QT_MAT_BAS"]
    + list(COLS_FAIXA_ETARIA.values())
    + list(COLS_ETAPA.values())
    + list(COLS_LOCALIZACAO_MATRICULA.values())
    + list(COLS_SEXO.values())
    + list(COLS_RACA.values())
)


def get_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("censo_escolar_bronze_to_gold")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def col_rede(tp_dependencia_col):
    return (
        F.when(tp_dependencia_col.isin(1, 2, 3), "Pública")
        .when(tp_dependencia_col == 4, "Privada")
        .otherwise("Não informado")
    )


def processar_ano(spark, ano: int):
    caminho = config.BRONZE_DIR / "escolas" / f"ano_censo={ano}"
    if not caminho.exists():
        print(f"[{ano}] bronze ausente, pulando (rode 02_landing_to_bronze.py antes).")
        return None

    bruto = spark.read.parquet(str(caminho))

    colunas_qt_presentes = [c for c in TODAS_COLS_QT_MAT if c in bruto.columns]
    faltando = set(TODAS_COLS_QT_MAT) - set(colunas_qt_presentes)
    if faltando:
        print(f"[{ano}] aviso: colunas ausentes neste ano (serão tratadas como 0): {sorted(faltando)}")

    selecao = [
        F.lit(ano).alias("ano_censo"),
        F.col(coluna_real("uf", ano, COLUNAS_ESCOLA)).alias("uf"),
        F.col(coluna_real("co_municipio", ano, COLUNAS_ESCOLA)).alias("co_municipio"),
        F.col(coluna_real("municipio", ano, COLUNAS_ESCOLA)).alias("municipio"),
        col_rede(F.col(coluna_real("dependencia_administrativa", ano, COLUNAS_ESCOLA)).cast("int")).alias("rede"),
    ]
    for c in colunas_qt_presentes:
        selecao.append(F.coalesce(F.col(c).cast("long"), F.lit(0)).alias(c))

    df = bruto.select(*selecao)

    agregacoes = [F.sum(c).alias(c) for c in colunas_qt_presentes]
    agregado = df.groupBy("ano_censo", "uf", "co_municipio", "municipio", "rede").agg(*agregacoes)

    for c in faltando:
        agregado = agregado.withColumn(c, F.lit(0).cast("long"))

    return agregado


def main():
    spark = get_spark()
    try:
        resultados = [r for r in (processar_ano(spark, ano) for ano in config.ANOS) if r is not None]
        if not resultados:
            print("Nenhum ano processado. Rode 01_download_landing.py e 02_landing_to_bronze.py primeiro.")
            return

        gold = resultados[0]
        for r in resultados[1:]:
            gold = gold.unionByName(r)

        total_linhas = gold.count()
        print(f"Gold agregado: {total_linhas:,} linhas (município x rede x ano — deve ser pequeno).")

        destino = config.GOLD_DIR / "matriculas_agregadas"
        gold.write.mode("overwrite").parquet(str(destino))
        print(f"Gravado em {destino}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
