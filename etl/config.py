"""Configuração central do pipeline ETL do Censo Escolar.

Importar este módulo ANTES de `pyspark` configura o ambiente Java/Hadoop
corretamente no Windows (ver docs/SETUP_AMBIENTE.md para o motivo de isso
precisar ser feito em Python e não via `set` do cmd.exe).
"""

import os
import sys
from pathlib import Path

# --- Ambiente PySpark no Windows (ajuste os caminhos para a sua máquina) ---
_JAVA_HOME = os.environ.get("JAVA_HOME", r"C:\Program Files\Java\jdk-17")
_HADOOP_HOME = os.environ.get("HADOOP_HOME", r"C:\Users\marcell.oliveira\hadoop")

os.environ["JAVA_HOME"] = _JAVA_HOME
os.environ["HADOOP_HOME"] = _HADOOP_HOME
os.environ["PATH"] = (
    os.path.join(_JAVA_HOME, "bin")
    + os.pathsep
    + os.path.join(_HADOOP_HOME, "bin")
    + os.pathsep
    + os.environ.get("PATH", "")
)
# Força (não usa setdefault): esta máquina tem PYSPARK_PYTHON=python3 e
# PYSPARK_DRIVER_PYTHON=jupyter configurados globalmente para outro uso, o
# que quebra a execução de scripts simples — sempre usar o Python do venv atual.
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
os.environ.pop("PYSPARK_DRIVER_PYTHON_OPTS", None)

# --- Caminhos do projeto ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LANDING_DIR = DATA_DIR / "landing"
BRONZE_DIR = DATA_DIR / "bronze"
GOLD_DIR = DATA_DIR / "gold"

for _d in (LANDING_DIR, BRONZE_DIR, GOLD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Censo Escolar (INEP) ---
ANOS = [2019, 2020, 2021, 2022, 2023]

URL_PATTERN = "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{ano}.zip"

REGIOES_MATRICULA = ["CO", "NORDESTE", "NORTE", "SUDESTE", "SUL"]

TABELAS_SIMPLES = ["ESCOLAS", "TURMAS", "DOCENTES"]

# --- Conexão com o Postgres/Supabase (camada gold) ---
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")
STAGING_SCHEMA = "staging"
