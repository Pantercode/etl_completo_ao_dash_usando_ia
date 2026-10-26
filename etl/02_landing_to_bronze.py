"""Bronze: lê o CSV bruto do INEP (;, latin1) e grava Parquet tipado, particionado por ano.

Desde 2019 o INEP consolida os microdados num ÚNICO arquivo por ano
(`microdados_ed_basica_{ano}.csv`), em nível de ESCOLA — com contagens de
matrícula já pré-agregadas por idade/etapa/zona/sexo/raça em colunas
QT_MAT_* (não existe mais um arquivo de matrícula por aluno). Por isso só há
uma "tabela" bronze aqui.

Sem lógica de negócio neste passo — só padronização de encoding/schema. As
derivações e agregações ficam no passo seguinte (03_bronze_to_gold.py).

Uso:
    python etl/02_landing_to_bronze.py
"""

import config  # precisa vir antes do pyspark: configura JAVA_HOME/HADOOP_HOME/PATH

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def get_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("censo_escolar_landing_to_bronze")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def encontrar_csv_principal(landing_dir):
    """O arquivo principal se chama `microdados_ed_basica_{ano}.csv` (ignora o suplemento de cursos técnicos)."""
    candidatos = [p for p in landing_dir.rglob("microdados_ed_basica_*.csv")]
    return candidatos[0] if candidatos else None


def processar_ano(spark: SparkSession, ano: int):
    landing_dir = config.LANDING_DIR / str(ano)
    if not landing_dir.exists():
        print(f"[{ano}] landing não encontrada em {landing_dir}, pulando (rode 01_download_landing.py antes).")
        return

    caminho_csv = encontrar_csv_principal(landing_dir)
    if caminho_csv is None:
        print(f"[{ano}] arquivo microdados_ed_basica_*.csv não encontrado, pulando.")
        return

    print(f"[{ano}] lendo {caminho_csv.name}...")
    df = (
        spark.read.option("header", True)
        .option("delimiter", ";")
        .option("encoding", "ISO-8859-1")  # equivalente a latin1/cp1252, padrão do INEP
        .option("inferSchema", True)
        .csv(str(caminho_csv))
        .withColumn("ano_censo", F.lit(ano))
    )

    n_linhas = df.count()
    n_colunas = len(df.columns)
    print(f"[{ano}] escolas: {n_linhas:,} linhas, {n_colunas} colunas")

    destino = config.BRONZE_DIR / "escolas" / f"ano_censo={ano}"
    df.write.mode("overwrite").parquet(str(destino))
    print(f"[{ano}] -> {destino}")


def main():
    spark = get_spark()
    try:
        for ano in config.ANOS:
            processar_ano(spark, ano)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
