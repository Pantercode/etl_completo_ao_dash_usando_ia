-- "Unpivot" das colunas QT_MAT_ZR_* (zona do aluno, não da escola) em linhas.
with base as (
    select ano_censo, uf, co_municipio, municipio, rede, qt_mat_urbana as valor, 'Urbana' as localizacao
    from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, co_municipio, municipio, rede, qt_mat_rural, 'Rural'
    from {{ ref('int_censo_unificado') }}
    union all
    select ano_censo, uf, co_municipio, municipio, rede, qt_mat_zona_nao_informada, 'Não informado'
    from {{ ref('int_censo_unificado') }}
)
select
    ano_censo,
    uf,
    co_municipio,
    municipio,
    localizacao,
    rede,
    sum(valor) as qtd_matriculas
from base
group by 1, 2, 3, 4, 5, 6
