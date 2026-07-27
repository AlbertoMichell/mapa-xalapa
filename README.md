# Mapa de direcciones de Xalapa, Veracruz

Página web autónoma con un mapa interactivo de **716 direcciones reales y
comprobadas** del municipio de Xalapa-Enríquez.

## Qué abrir

**`mapa_xalapa.html`** — un solo archivo, doble clic y funciona. Lleva dentro el
HTML, el CSS, el JavaScript y los datos. Necesita conexión a internet únicamente
para las teselas del mapa y la librería Leaflet, que se sirven por CDN.

## Objetivo del sistema

El listado de partida (`direcciones.md`) era texto plano sin coordenadas, con la
mitad del contenido duplicado y con domicilios escritos de forma irregular. El
sistema lo convierte en un dataset georreferenciado y **auditable**: cada punto
conserva de dónde salió su coordenada y con qué identificador de OpenStreetMap
se puede volver a comprobar.

El criterio rector es **no inventar**. Cuando una dirección no se pudo ubicar
con precisión de inmueble, se conserva al nivel que sí se pudo verificar
(vialidad, cruce o colonia) y así queda etiquetada en el mapa, en lugar de
fabricar una coordenada que aparente exactitud.

## Qué permite hacer el mapa

- Ver las 716 direcciones sobre el mapa de Xalapa, agrupadas por concentración.
- Filtrar por nombre, dirección o colonia; por tipo de oficina (pública,
  privada, mixta, sin determinar); por categoría; por origen del dato; y por
  precisión mínima de la ubicación.
- Fijar cualquier punto como **origen** y filtrar por **radio** (0–8 km).
- Consultar, de cualquier punto, **los 8 más cercanos** con su distancia.
- Medir la distancia entre dos lugares cualesquiera del mapa (**Medir A→B**).
- Exportar el listado filtrado a CSV o generar la **matriz de distancias**
  completa entre todas las direcciones visibles.
- Superponer el **mapa de calor** de densidad, las **zonas habitacionales**
  (polígonos reales `landuse=residential`), las colonias y el límite municipal.

## Sobre la densidad de personas

Las fuentes empleadas **no publican población por colonia**, así que el mapa no
la inventa. Lo que sí presenta, calculado con datos reales:

- Población y densidad municipales (443,063 habitantes; 3,561 hab/km² sobre los
  124.4 km² del polígono municipal de OSM).
- Superficie habitacional cartografiada (1.77 km² en 26 polígonos).
- Concentración de puntos por km² y conteo por colonia, que se recalculan con
  cada filtro que apliques.

## Procedencia y verificación

| Fuente | Uso |
|---|---|
| `direcciones.md` | Listado original: 75 registros únicos (de 150 líneas, la mitad duplicadas) |
| Overpass API / OpenStreetMap | POIs, vialidades con numeración, zonas habitacionales, colonias |
| Nominatim | Geocodificación directa e inversa, límite municipal |
| orfis.gob.mx, cespver.gob.mx, bienestar.gob.mx | Confirmación de tres domicilios que no resolvían |

Controles aplicados a los 716 puntos, todos superados:

- **Límite municipal**: cada coordenada se prueba contra el polígono real de
  Xalapa (OSM `relation/6037863`). Este filtro descartó coincidencias que caían
  en Rafael Lucio y Emiliano Zapata.
- **Colisiones**: un mismo objeto de OSM no puede representar a dos registros
  distintos; el de menor confianza se reasigna por domicilio.
- **Coordenadas repetidas**: se distingue entre oficinas que comparten inmueble
  (legítimo) y direcciones distintas colapsadas en un punto (error).
- **Cotejo inverso**: cada coordenada se geocodifica de vuelta y se contrasta
  contra el domicilio declarado.

Resultado sobre el listado original: **0 errores**, 21 registros sin
observaciones y 54 con avisos (en su gran mayoría, discrepancias de código
postal entre OSM y el archivo, que en México son frecuentes y no concluyentes).

Precisión alcanzada: 669 puntos ubicados en el inmueble, 5 en número oficial
levantado en campo, 6 interpolados entre números levantados, 9 en el número más
cercano, 3 en inmueble compartido, 2 en cruce de vialidades, 17 a nivel de
vialidad, 2 a nivel de colonia y 3 aproximados.

## Regenerar los datos

```bash
python tools/build.py      # pipeline completo
python tools/reporte.py    # resumen de calidad
```

El pipeline es idempotente y cachea las respuestas de red en `data/`, así que
volver a correrlo no repite descargas.

| Script | Función |
|---|---|
| `parse_md.py` | Extrae y deduplica las entradas de `direcciones.md` |
| `osm_fetch.py` | Descarga POIs de Xalapa por categoría |
| `zonas_fetch.py` | Descarga geometría de zonas habitacionales y colonias |
| `boundary.py` | Polígono municipal y prueba punto-en-polígono |
| `geocode.py` | Geocodifica el listado; filtro municipal y resolución de colisiones |
| `resolve_pending.py` | Resuelve casos puntuales por cruce, inmueble compartido u objeto OSM |
| `interp_num.py` | Afina ubicaciones interpolando por número oficial |
| `verify.py` | Cotejo inverso y clasificación de errores/avisos |
| `enrich.py` | Da domicilio, colonia, CP y sector a los POIs de OSM |
| `merge.py` | Fusiona todo en `data/dataset.json` |
| `make_app.py` | Incrusta el dataset en la plantilla y genera el HTML final |

## Licencia de los datos

Los datos geográficos provienen de OpenStreetMap y sus colaboradores, bajo
licencia ODbL. La atribución aparece en el propio mapa.
