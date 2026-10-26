select
    ano_censo,
    uf,
    rede,
    sum(qt_mat_bas) as qtd_matriculas
from {{ ref('int_censo_unificado') }}
group by 1, 2, 3
order by ano_censo
