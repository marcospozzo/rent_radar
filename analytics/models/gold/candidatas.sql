-- Publicaciones que cumplen los criterios de la búsqueda a la que pertenecen
-- (silver.busquedas, cargada desde alerts.yaml): una fila por búsqueda y
-- publicación. El filtro de los portales no alcanza: ignoran algunos criterios
-- y dejan pasar avisos en otra moneda.
--
-- Todo se compara en pesos. Las expensas vienen en pesos aunque el precio esté
-- en dólares.
select
    p.*,
    b.id_busqueda
from {{ ref('publicaciones') }} p
inner join {{ ref('publicaciones_busquedas') }} pb
    on pb.fuente = p.fuente
   and pb.id_publicacion = p.id_publicacion
inner join silver.busquedas b
    on b.id_busqueda = pb.id_busqueda
-- Ambientes o superficie desconocidos pasan: el portal ya filtró por ellos y perder
-- un aviso por un dato que no se pudo leer es peor que mostrar uno de más.
where (p.ambientes is null or p.ambientes >= b.ambientes_min)
  and (p.ambientes is null or b.ambientes_max is null or p.ambientes <= b.ambientes_max)
  and coalesce(p.cocheras, 0) >= b.cocheras_min
  and (b.superficie_min_m2 is null
       or coalesce(p.superficie_cubierta, p.superficie_total) is null
       or coalesce(p.superficie_cubierta, p.superficie_total) >= b.superficie_min_m2)
  and (
      b.precio_max is null
      or (case p.moneda when 'USD' then p.precio * {{ var('tipo_cambio_usd') }} else p.precio end
          + coalesce(p.expensas, 0))
         <= case b.moneda when 'USD' then b.precio_max * {{ var('tipo_cambio_usd') }} else b.precio_max end
  )
