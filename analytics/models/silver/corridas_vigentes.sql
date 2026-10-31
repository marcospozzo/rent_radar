{{ config(materialized='table') }}

-- La última corrida exitosa de cada portal para cada búsqueda activa. Cada portal
-- se toma por separado: un bloqueo en uno no debe tirar a cero lo que se ve de
-- los otros. Las corridas de búsquedas inactivas o borradas del YAML (y las
-- anteriores a las búsquedas, sin id_busqueda) quedan afuera.

select distinct on (r.fuente, r.id_busqueda)
    r.id_ejecucion,
    r.fuente,
    r.id_busqueda
from raw.pipeline_runs r
inner join silver.busquedas b
    on b.id_busqueda = r.id_busqueda
   and b.activa
where r.estado = 'ok'
order by r.fuente, r.id_busqueda, r.finalizado_en desc
