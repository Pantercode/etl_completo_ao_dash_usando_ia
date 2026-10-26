-- "Unpivot" das colunas QT_MAT_{etapa} em linhas (uma por etapa de ensino).
-- Atenção: QT_MAT_ESP (educação especial) pode se sobrepor com as demais etapas.
with base as (
    select ano_censo, uf, rede, qt_mat_infantil as valor, 'Educação Infantil' as etapa_ensino from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_fundamental, 'Ensino Fundamental' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_medio, 'Ensino Médio' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_profissional, 'Educação Profissional' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_eja, 'EJA' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_especial, 'Educação Especial' from {{ ref('int_censo_unificado') }}
)
select
    ano_censo,
    uf,
    rede,
    etapa_ensino,
    sum(valor) as qtd_matriculas
from base
group by 1, 2, 3, 4
