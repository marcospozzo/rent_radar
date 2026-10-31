{{ config(materialized='table') }}

with base as (
    select s.*
    from raw.snapshots s
    inner join {{ ref('corridas_vigentes') }} cv on s.id_ejecucion = cv.id_ejecucion
),

deduped as (
    -- Por (fuente, id_publicacion) nos quedamos con el snapshot más reciente
    select distinct on (fuente, id_publicacion)
        *
    from base
    order by fuente, id_publicacion, fecha_scraping desc
),

specs_parsed as (
    -- Extrae campos estructurados desde el array especificaciones según el formato de cada portal.
    -- ZonaProp:     "200 m² tot." / "115 m² cub." / "1 coch." / "55 años"
    -- Argenprop:    "82 m² Cubierta" o "Sup. Cubierta: 82 m2"
    --               "385 m² Terreno" o "Sup. Total: 115 m2"
    --               "1 cochera" / "55 años"
    -- MercadoLibre: "Superficie cubierta: 118 m²" / "Superficie total: 151 m²"
    --               "Cocheras: 1" / "Antigüedad: 55 años" / "Ambientes: 3"
    select
        d.id,
        max(case
            when d.fuente = 'zonaprop'     and s.spec ~* '\d+\s*m²\s*cub'
                then (regexp_match(s.spec, '(\d+)\s*m', 'i'))[1]::numeric
            when d.fuente = 'argenprop'    and s.spec ~* 'm²\s*cubierta'
                then (regexp_match(s.spec, '(\d+)\s*m', 'i'))[1]::numeric
            when d.fuente = 'argenprop'    and s.spec ~* '^sup\.\s*cubierta\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
            when d.fuente = 'mercadolibre' and s.spec ~* '^superficie\s+cubierta\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
        end) as superficie_cubierta,
        max(case
            when d.fuente = 'zonaprop'     and s.spec ~* '\d+\s*m²\s*tot'
                then (regexp_match(s.spec, '(\d+)\s*m', 'i'))[1]::numeric
            when d.fuente = 'argenprop'    and s.spec ~* 'm²\s*terreno'
                then (regexp_match(s.spec, '(\d+)\s*m', 'i'))[1]::numeric
            when d.fuente = 'argenprop'    and s.spec ~* '^sup\.\s*total\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
            when d.fuente = 'mercadolibre' and s.spec ~* '^superficie\s+total\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
        end) as superficie_total,
        max(case
            when d.fuente = 'zonaprop'     and s.spec ~* '^\d+\s*coch'
                then (regexp_match(s.spec, '^(\d+)', 'i'))[1]::numeric
            when d.fuente = 'argenprop'    and s.spec ~* '^\d+\s*cochera'
                then (regexp_match(s.spec, '^(\d+)', 'i'))[1]::numeric
            when d.fuente = 'mercadolibre' and s.spec ~* '^cocheras\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
        end) as cocheras,
        max(case
            when d.fuente in ('zonaprop', 'argenprop') and s.spec ~* '^\d+\s*años'
                then (regexp_match(s.spec, '^(\d+)', 'i'))[1]::numeric
            when d.fuente = 'mercadolibre' and s.spec ~* '^antig'
                then (regexp_match(s.spec, '(\d+)\s*años?', 'i'))[1]::numeric
        end) as antiguedad,
        max(case
            when d.fuente = 'mercadolibre' and s.spec ~* '^ambientes\s*:'
                then (regexp_match(s.spec, ':\s*(\d+)', 'i'))[1]::numeric
        end) as spec_ambientes
    from deduped d
    left join lateral unnest(d.especificaciones) as s(spec) on true
    group by d.id
),

candidatos as (
    -- Solo publicaciones residenciales de alquiler participan en el cruce cross-portal.
    -- Uso comercial y venta/permuta generan falsos positivos al compartir coordenadas
    -- con propiedades residenciales distintas en el mismo bucket.
    select * from deduped
    where titulo not ilike '%uso comercial%'
      and titulo not ilike '%solo comercial%'
      and titulo not ilike '%venta permuta%'
),

duplicados as (
    -- Detecta pares que son la misma propiedad (mismo portal o portales distintos):
    -- a <= 120m de distancia real, mismos ambientes, misma moneda y precio
    -- dentro del ±10%. Incluye duplicados dentro del mismo portal (inmobiliarias
    -- que repostean el mismo aviso con otro id_publicacion).
    -- Antes se comparaba round(lat,3)=round(lat,3) (bucket de ±0.001° ≈ 111m):
    -- dos coordenadas a 80m reales una de otra pero a los dos lados del borde
    -- de esa grilla (ej. longitud -58.5588 vs -58.5584, que redondean a
    -- -58.559 y -58.558) no matcheaban y el duplicado se colaba. Con distancia
    -- real (misma aproximación plana que usa distance_to_center_km más abajo)
    -- ese caso de borde queda cubierto.
    -- De cada par se marca para eliminar el que tenga especificaciones más cortas;
    -- en empate, se descarta el de id mayor (más nuevo).
    select distinct
        case
            when coalesce(array_length(a.especificaciones, 1), 0)
               > coalesce(array_length(b.especificaciones, 1), 0)
                then b.id
            when coalesce(array_length(b.especificaciones, 1), 0)
               > coalesce(array_length(a.especificaciones, 1), 0)
                then a.id
            else greatest(a.id, b.id)
        end as id_a_eliminar
    from candidatos a
    join candidatos b
        on a.id < b.id
        and a.moneda     = b.moneda
        and a.ambientes  = b.ambientes
        and a.moneda    is not null
        and a.ambientes is not null
        and a.precio    is not null
        and b.precio    is not null
        and a.latitud   is not null
        and a.longitud  is not null
        and b.latitud   is not null
        and b.longitud  is not null
        and sqrt(
                power((a.latitud - b.latitud) * {{ km_per_degree_lat() }}, 2)
              + power(
                    (a.longitud - b.longitud) * {{ km_per_degree_lat() }} * cos(radians(a.latitud)),
                    2
                )
            ) <= 0.12
        and abs(a.precio::float - b.precio::float)
            / greatest(a.precio, b.precio)::float <= 0.10
),

enriched as (
    -- Aplica COALESCE(raw, specs) para ambientes y añade columnas nuevas desde specs.
    -- Las coordenadas prefieren silver.coordenadas_override (ver geocode_fallback.py)
    -- sobre las del portal: algunos portales geocodifican mal una dirección correcta.
    select
        d.id,
        d.id_ejecucion,
        d.fuente,
        d.id_publicacion,
        d.url,
        d.titulo,
        d.precio,
        d.moneda,
        d.expensas,
        d.ubicacion,
        coalesce(co.latitud,  d.latitud)  as latitud,
        coalesce(co.longitud, d.longitud) as longitud,
        coalesce(d.ambientes, sp.spec_ambientes) as ambientes,
        sp.superficie_cubierta,
        sp.superficie_total,
        sp.cocheras,
        sp.antiguedad,
        d.publicado_en,
        d.fecha_scraping,
        d.vendedor,
        d.especificaciones
    from deduped d
    left join specs_parsed sp on d.id = sp.id
    left join silver.coordenadas_override co
        on co.fuente = d.fuente and co.id_publicacion = d.id_publicacion
),

zone_center as (
    -- Centro de la zona buscada = mediana de lat/lon de las propias publicaciones.
    -- No se hardcodea ningún punto fijo: si las URLs de búsqueda en run_ingest.py
    -- cambian de zona, el centro se recalcula solo en la próxima corrida.
    -- La mediana es robusta a outliers, así 1-2 publicaciones mal geocodificadas
    -- no corren el centro.
    select
        percentile_cont(0.5) within group (order by latitud)  as center_lat,
        percentile_cont(0.5) within group (order by longitud) as center_lon
    from enriched
    where latitud is not null and longitud is not null
      and latitud < 0 and longitud < 0
),

distances as (
    select
        e.id,
        sqrt(
            power((e.latitud - zc.center_lat) * {{ km_per_degree_lat() }}, 2)
          + power((e.longitud - zc.center_lon) * {{ km_per_degree_lat() }} * cos(radians(zc.center_lat)), 2)
        ) as distance_to_center_km
    from enriched e
    cross join zone_center zc
    where e.latitud is not null and e.longitud is not null
),

zone_radius as (
    -- Radio = cerca-lejos de Tukey (Q3 + 3·RIC) sobre las distancias al centro: un
    -- criterio estadístico estándar para separar errores genuinos de geocodificación
    -- del portal de origen (casi siempre a cientos de km) de zonas de búsqueda
    -- legítimas pero más alejadas del centro (ver URLs nuevas en run_ingest.py).
    -- A diferencia de mediana*4, que solo capta el ancho del cluster dominante, este
    -- se adapta a la dispersión real de los puntos válidos: agregar una zona nueva
    -- (ej. Caballito) no la descarta por estar "lejos" del centro de la zona vieja.
    -- Piso de 5km para no sobre-ajustar si hay pocas publicaciones.
    select
        greatest(
            percentile_cont(0.75) within group (order by distance_to_center_km)
            + 3 * (
                percentile_cont(0.75) within group (order by distance_to_center_km)
              - percentile_cont(0.25) within group (order by distance_to_center_km)
            ),
            5
        ) as radius_km
    from distances
),

filtered as (
    select
        e.*,
        d.distance_to_center_km,
        case
            when e.titulo ilike '%uso comercial%'
              or e.titulo ilike '%solo comercial%'                        then 'uso_comercial'
            when e.titulo ilike '%venta permuta%'                        then 'venta_permuta'
            when e.url           is null                                 then 'url_nula'
            when e.titulo        is null                                 then 'titulo_nulo'
            when e.precio        is null                                 then 'precio_nulo'
            when e.moneda        is null                                 then 'moneda_nula'
            when e.ubicacion     is null                                 then 'ubicacion_nula'
            when e.latitud       is null                                 then 'latitud_nula'
            when e.longitud      is null                                 then 'longitud_nula'
            when e.ambientes     is null                                 then 'ambientes_nulo'
            when coalesce(e.superficie_cubierta, e.superficie_total) is null then 'superficie_nula'
            when e.latitud  >= 0                                         then 'latitud_invalida'
            when e.longitud >= 0                                         then 'longitud_invalida'
            when d.distance_to_center_km > zr.radius_km                     then 'coordenadas_fuera_de_zona'
            when e.ambientes     = 0                                     then 'ambientes_cero'
            when coalesce(e.superficie_cubierta, e.superficie_total) = 0 then 'superficie_cero'
            when e.precio = 9999999                                      then 'precio_placeholder'
            when e.moneda = 'ARS' and e.precio < 500000                  then 'precio_ars_bajo'
            when e.moneda = 'ARS' and e.precio > 3000000                 then 'precio_ars_alto'
            when e.moneda = 'USD' and e.precio < 100                     then 'precio_usd_bajo'
            when e.moneda = 'USD' and e.precio > 3000                    then 'precio_usd_alto'
            else null
        end as motivo_rechazo
    from enriched e
    left join distances d on d.id = e.id
    cross join zone_radius zr
    where e.id not in (select id_a_eliminar from duplicados)
)

select
    id,
    id_ejecucion,
    fuente,
    id_publicacion,
    url,
    titulo,
    precio,
    moneda,
    expensas,
    ubicacion,
    latitud,
    longitud,
    ambientes,
    superficie_cubierta,
    superficie_total,
    cocheras,
    antiguedad,
    publicado_en,
    fecha_scraping,
    vendedor,
    especificaciones
from filtered
where motivo_rechazo is null
