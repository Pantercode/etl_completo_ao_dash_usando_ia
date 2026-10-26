-- Limpeza/padronização comum compartilhada por todos os marts diamond.
select
    ano_censo,
    upper(trim(uf)) as uf,
    co_municipio,
    trim(municipio) as municipio,
    coalesce(rede, 'Não informado') as rede,
    qt_mat_bas,
    qt_mat_0_3,
    qt_mat_4_5,
    qt_mat_6_10,
    qt_mat_11_14,
    qt_mat_15_17,
    qt_mat_18_mais,
    qt_mat_infantil,
    qt_mat_fundamental,
    qt_mat_medio,
    qt_mat_profissional,
    qt_mat_eja,
    qt_mat_especial,
    qt_mat_urbana,
    qt_mat_rural,
    qt_mat_zona_nao_informada
from {{ ref('stg_matriculas_agregadas') }}
