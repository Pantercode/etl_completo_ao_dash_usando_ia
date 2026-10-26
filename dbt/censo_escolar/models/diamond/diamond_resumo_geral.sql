-- KPIs de topo do dashboard: um registro por ano.
select
    ano_censo,
    sum(qt_mat_bas) as total_matriculas,
    sum(case when rede = 'Pública' then qt_mat_bas else 0 end) as total_rede_publica,
    sum(case when rede = 'Privada' then qt_mat_bas else 0 end) as total_rede_privada,
    sum(qt_mat_urbana) as total_urbana,
    sum(qt_mat_rural) as total_rural,
    count(distinct uf) as qtd_ufs,
    count(distinct co_municipio) as qtd_municipios
from {{ ref('int_censo_unificado') }}
group by 1
order by 1
