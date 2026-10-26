-- 1:1 com a tabela carregada pelo PySpark em staging.matriculas_agregadas
-- (uma linha por ano x UF x município x rede, já com as contagens QT_MAT_* somadas)
select
    ano_censo,
    uf,
    co_municipio,
    municipio,
    rede,
    "QT_MAT_BAS" as qt_mat_bas,
    "QT_MAT_BAS_0_3" as qt_mat_0_3,
    "QT_MAT_BAS_4_5" as qt_mat_4_5,
    "QT_MAT_BAS_6_10" as qt_mat_6_10,
    "QT_MAT_BAS_11_14" as qt_mat_11_14,
    "QT_MAT_BAS_15_17" as qt_mat_15_17,
    "QT_MAT_BAS_18_MAIS" as qt_mat_18_mais,
    "QT_MAT_INF" as qt_mat_infantil,
    "QT_MAT_FUND" as qt_mat_fundamental,
    "QT_MAT_MED" as qt_mat_medio,
    "QT_MAT_PROF" as qt_mat_profissional,
    "QT_MAT_EJA" as qt_mat_eja,
    "QT_MAT_ESP" as qt_mat_especial,
    "QT_MAT_ZR_URB" as qt_mat_urbana,
    "QT_MAT_ZR_RUR" as qt_mat_rural,
    "QT_MAT_ZR_NA" as qt_mat_zona_nao_informada
from {{ source('staging', 'matriculas_agregadas') }}
