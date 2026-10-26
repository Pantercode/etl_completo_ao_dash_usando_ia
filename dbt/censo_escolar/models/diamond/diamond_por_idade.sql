-- "Unpivot" das colunas QT_MAT_{faixa} em linhas (uma por faixa etária).
with base as (
    select ano_censo, uf, rede, qt_mat_0_3 as valor, '0-3' as faixa_etaria from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_4_5, '4-5' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_6_10, '6-10' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_11_14, '11-14' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_15_17, '15-17' from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, rede, qt_mat_18_mais, '18+' from {{ ref('int_censo_unificado') }}
)
select
    ano_censo,
    uf,
    rede,
    faixa_etaria,
    sum(valor) as qtd_matriculas
from base
group by 1, 2, 3, 4
