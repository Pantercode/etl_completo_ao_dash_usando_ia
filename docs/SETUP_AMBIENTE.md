# Setup do ambiente (Windows) — PySpark + dbt

Este guia foi validado nesta máquina (Python 3.14, Java 21/17 instalados, Windows 11). Se você estiver em outra máquina, os passos são os mesmos, só ajuste as versões se necessário.

## 1. Java (JDK)

PySpark precisa de um JDK (17 ou 21 funcionam bem com o Spark atual). Se já tiver um JDK 17 ou 21 instalado, pode reaproveitar — não precisa ser exclusivo deste projeto.

Verifique o que já existe:

```powershell
Get-ChildItem "C:\Program Files\Java"
```

Se não tiver nenhum, baixe o JDK 17 (Temurin/Adoptium ou Oracle) e instale normalmente.

**Importante**: não é necessário (nem recomendado) alterar a variável `JAVA_HOME` do Windows globalmente. Vamos configurar isso **dentro dos próprios scripts Python**, o que evita um bug bem conhecido do `cmd.exe` no Windows (explicado na seção de troubleshooting).

## 2. Python + PySpark

Qualquer Python 3.11+ funciona (testado aqui com Python 3.14 e PySpark 4.2.0, sem problemas). Crie um ambiente virtual dedicado ao projeto:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r etl\requirements.txt
```

## 3. winutils.exe + hadoop.dll (obrigatório no Windows)

O Spark no Windows precisa de dois binários nativos do Hadoop para conseguir **escrever arquivos locais** (Parquet, etc.) — sem eles, o PySpark até cria a `SparkSession` e faz `.show()`, mas qualquer `.write.parquet(...)` falha.

1. Baixe `winutils.exe` e `hadoop.dll` de um repositório confiável, por exemplo:
   - https://github.com/cdarlint/winutils (pasta `hadoop-3.3.5/bin`, bem estabelecido e usado há anos)
2. Coloque os dois arquivos em uma pasta fixa, por exemplo:
   ```
   C:\Users\<seu_usuario>\hadoop\bin\winutils.exe
   C:\Users\<seu_usuario>\hadoop\bin\hadoop.dll
   ```
3. Você vai apontar `HADOOP_HOME` para `C:\Users\<seu_usuario>\hadoop` (sem o `\bin`) — isso é feito no próprio script Python, veja a próxima seção.

## 4. Configuração dentro dos scripts (a parte que realmente importa)

**Não faça isso via `set VAR=... && set PATH=...%VAR%...` numa linha só do `cmd.exe`** — por uma peculiaridade de como o `cmd.exe` expande variáveis (ele expande a linha inteira **antes** de executar qualquer comando dela), `%JAVA_HOME%`/`%HADOOP_HOME%` ficam com o valor **anterior** (vazio) mesmo que você tenha acabado de definir na mesma linha. Isso gera erros confusos como `A sintaxe do comando está incorreta` ou `UnsatisfiedLinkError` mesmo com tudo "aparentemente" configurado certo.

A forma robusta e multiplataforma é configurar o ambiente **dentro do próprio Python**, antes de importar o `pyspark`. Todos os scripts do `etl/` já fazem isso via `etl/config.py`:

```python
import os

os.environ["JAVA_HOME"] = r"C:\Program Files\Java\jdk-17"
os.environ["HADOOP_HOME"] = r"C:\Users\marcell.oliveira\hadoop"
os.environ["PATH"] = os.environ["JAVA_HOME"] + r"\bin;" + os.environ["HADOOP_HOME"] + r"\bin;" + os.environ["PATH"]
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from pyspark.sql import SparkSession  # só importar depois de setar o ambiente acima
```

`PYSPARK_PYTHON`/`PYSPARK_DRIVER_PYTHON` também são importantes: sem eles, o script interno do PySpark (`find-spark-home.cmd`) tenta localizar um `python3` genérico no PATH e, se não encontrar, cai num trecho de batch com um bug de sintaxe conhecido no Windows. Apontar explicitamente para o Python do seu venv evita isso completamente.

## 5. Testando

Depois de configurar `etl/config.py` com os caminhos corretos da sua máquina, teste com:

```powershell
.venv\Scripts\python.exe -c "from etl import config; from pyspark.sql import SparkSession; s = SparkSession.builder.master('local[2]').getOrCreate(); s.createDataFrame([(1,'a')], ['id','v']).write.mode('overwrite').parquet('data/bronze/_teste'); print('OK')"
```

Se aparecer `OK` sem erro, o ambiente está pronto.

## 6. dbt

```powershell
pip install dbt-core dbt-postgres
cd dbt\censo_escolar
dbt debug   # confirma a conexão com o Supabase (configure profiles.yml antes, ver dbt/censo_escolar/profiles.yml.example)
```

## Troubleshooting (erros reais encontrados ao validar este guia)

- **`A sintaxe do comando está incorreta.` ao rodar qualquer coisa do PySpark** → quase sempre é o bug de expansão de variável do `cmd.exe` descrito na seção 4, ou `PYSPARK_PYTHON` não configurado. Configure o ambiente em Python, não em uma linha de `cmd.exe`.
- **`UnsatisfiedLinkError: ... NativeIO$Windows.access0` ao escrever Parquet** → `hadoop.dll` não está sendo encontrado no `PATH` real do processo (normalmente porque `HADOOP_HOME\bin` não chegou a entrar no `PATH` de verdade — mesmo bug de expansão). Confirme configurando tudo em Python como na seção 4.
- **`A sintaxe do comando está incorreta` mesmo seguindo a seção 4** → se esta máquina já tem `PYSPARK_PYTHON`/`PYSPARK_DRIVER_PYTHON` configurados globalmente para outro uso (ex: Jupyter), eles têm prioridade sobre um `os.environ.setdefault(...)` no script. `etl/config.py` por isso **sobrescreve** essas variáveis à força em vez de usar `setdefault`.
- **`SSLCertVerificationError: unable to get local issuer certificate` ao baixar os dados do INEP** → sites `.gov.br` usam certificados raiz da ICP-Brasil, que o Windows confia nativamente mas o bundle de CAs do Python (`certifi`) não. O `01_download_landing.py` já resolve isso chamando `truststore.inject_into_ssl()` antes de importar `requests`, o que faz o Python usar o certificate store do Windows em vez do bundle próprio.
- **`HADOOP_HOME and hadoop.home.dir are unset`** → falta baixar o `winutils.exe`/`hadoop.dll` (seção 3) ou `HADOOP_HOME` não está apontando pra pasta certa (deve apontar para a pasta que **contém** `bin\winutils.exe`, não para o `bin` em si).
