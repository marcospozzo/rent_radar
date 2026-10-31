{{ config(materialized='table') }}

-- A qué búsquedas pertenece cada publicación: las que aparecieron en la última
-- corrida vigente de su portal. Una misma propiedad puede pertenecer a varias.

select distinct
    s.fuente,
    s.id_publicacion,
    cv.id_busqueda
from raw.snapshots s
inner join {{ ref('corridas_vigentes') }} cv on s.id_ejecucion = cv.id_ejecucion
