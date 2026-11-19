.PHONY: landing bronze gold load dbt-run dbt-test pipeline dashboard

landing:
	python etl/01_download_landing.py

bronze:
	python etl/02_landing_to_bronze.py

gold:
	python etl/03_bronze_to_gold.py

load:
	python etl/04_load_gold_to_duckdb.py

dbt-run:
	cd dbt/censo_escolar && dbt run --profiles-dir .

dbt-test:
	cd dbt/censo_escolar && dbt test --profiles-dir .

pipeline: landing bronze gold load dbt-run dbt-test

dashboard:
	cd dashboard && python app.py
