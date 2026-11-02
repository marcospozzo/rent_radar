{% macro km_per_degree_lat() %}
{#
    Kilómetros por grado de latitud (circunferencia terrestre ≈ 40.008km / 360°).
    Sirve para aproximar distancias cortas sin Haversine/PostGIS: 1 grado de
    longitud equivale a esto mismo multiplicado por cos(latitud), porque los
    meridianos se acercan entre sí cerca de los polos.
    Usado por publicaciones.sql para detectar el mismo inmueble publicado más de
    una vez (ver el CTE duplicados).
#}
111.32
{% endmacro %}
