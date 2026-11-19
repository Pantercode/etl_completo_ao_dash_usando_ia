-- Usa o "+schema" configurado tal como está (diamond, staging...), sem o prefixo
-- padrão do dbt ("main_diamond"): o dashboard lê de diamond.<tabela>.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
