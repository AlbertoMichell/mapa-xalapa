# -*- coding: utf-8 -*-
"""Fusiona el listado original con los POIs de OSM y arma data/dataset.json.

Reglas de fusion:
  - Los registros de direcciones.md mandan: conservan su nombre y su contexto.
  - Si un registro ya quedo anclado a un objeto OSM, ese objeto no se repite.
  - Ademas se descarta el POI que coincide en nombre y cae a menos de 40 m de
    un registro del listado original.
"""
import io, json, math, os, re, sys, unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OSMDIR = os.path.join(DATA, "osm")
OUT = os.path.join(DATA, "dataset.json")

# Poblacion municipal de Xalapa segun el censo INEGI 2020, tal como aparece
# etiquetada en OSM. No existe dato de poblacion por colonia en estas fuentes.
POBLACION_CIUDAD = 443063


def sa(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def toks(s):
    return set(w for w in re.sub(r"[^a-z0-9 ]+", " ", sa(s)).split() if len(w) > 3)


def hav(la1, lo1, la2, lo2):
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def area_m2(ring):
    """Area geodesica aproximada de un anillo [(lat,lon),...] en metros^2."""
    if len(ring) < 3:
        return 0.0
    lat0 = sum(p[0] for p in ring) / len(ring)
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    s = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i][1] * kx, ring[i][0] * ky
        x2, y2 = ring[(i + 1) % len(ring)][1] * kx, ring[(i + 1) % len(ring)][0] * ky
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


CATEGORIA_SEED = [
    (r"fiscal|tribunal|juzgado|judicial|justicia|notaria|conciliacion|registro publico", "justicia"),
    (r"seguridad|policia|proteccion civil", "seguridad"),
    (r"salud|imss|issste|sesver|hospital|dif ", "salud"),
    (r"educacion|sev\b|universidad|escuela|primarias", "educacion"),
    (r"banamex|santander|financiera|banco", "financiero"),
]


def categoria_seed(nombre):
    n = sa(nombre)
    for pat, cat in CATEGORIA_SEED:
        if re.search(pat, n):
            return cat
    return "gobierno"


def cargar_zonas(rings):
    zonas = []
    p = os.path.join(OSMDIR, "habitacional_geom.json")
    if not os.path.exists(p):
        return zonas
    for el in json.load(io.open(p, encoding="utf-8"))["elements"]:
        g = el.get("geometry") or []
        ring = [(pt["lat"], pt["lon"]) for pt in g if pt]
        if len(ring) < 4:
            continue
        cy = sum(x[0] for x in ring) / len(ring)
        cx = sum(x[1] for x in ring) / len(ring)
        if not boundary.point_in(rings, cy, cx):
            continue
        zonas.append({"nombre": (el.get("tags") or {}).get("name", "Zona habitacional"),
                      "ref": "way/%s" % el.get("id"),
                      "area_ha": round(area_m2(ring) / 10000.0, 2),
                      "centro": [round(cy, 6), round(cx, 6)],
                      "poligono": [[round(a, 6), round(b, 6)] for a, b in ring]})
    return zonas


def cargar_colonias(rings):
    cols = []
    p = os.path.join(OSMDIR, "colonias_geom.json")
    if not os.path.exists(p):
        return cols
    for el in json.load(io.open(p, encoding="utf-8"))["elements"]:
        t = el.get("tags") or {}
        if not t.get("name"):
            continue
        if el.get("type") == "node":
            lat, lon, poly = el["lat"], el["lon"], None
        else:
            g = [(pt["lat"], pt["lon"]) for pt in (el.get("geometry") or []) if pt]
            if len(g) < 4:
                continue
            lat = sum(x[0] for x in g) / len(g)
            lon = sum(x[1] for x in g) / len(g)
            poly = [[round(a, 6), round(b, 6)] for a, b in g]
        if not boundary.point_in(rings, lat, lon):
            continue
        cols.append({"nombre": t["name"], "tipo": t.get("place", ""),
                     "lat": round(lat, 6), "lon": round(lon, 6),
                     "poblacion": int(t["population"]) if str(t.get("population", "")).isdigit() else None,
                     "poligono": poly})
    return cols


def main():
    rings = boundary.ensure()["rings"]
    seed = json.load(io.open(os.path.join(DATA, "seed_geo.json"), encoding="utf-8"))
    try:
        osm = json.load(io.open(os.path.join(DATA, "osm_pois.json"), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        print("!! falta osm_pois.json (corre enrich.py); se sigue solo con el listado")
        osm = []

    puntos, usados = [], set()
    for i, r in enumerate(seed):
        if r.get("lat") is None:
            continue
        ctrl = r.get("control") or {}
        if r.get("ref"):
            usados.add(r["ref"])
        puntos.append({
            "id": "md-%03d" % i,
            "nombre": r["nombre"],
            "direccion": r["direccion"],
            "colonia": ctrl.get("colonia", ""),
            "cp": ctrl.get("cp", ""),
            "lat": round(r["lat"], 6), "lon": round(r["lon"], 6),
            "sector": r.get("sector", "publica"),
            "categoria": categoria_seed(r["nombre"]),
            "zona": r.get("zona", ""),
            "precision": r.get("precision", ""),
            "verificacion": r.get("verificacion", ""),
            "ref": r.get("ref", ""),
            "cotejo": ctrl.get("direccion_osm", ""),
            "nota": r.get("nota", ""),
            "fuente": "direcciones.md",
        })

    # --- POIs de OSM que no dupliquen algo del listado original
    descartados = 0
    for j, p in enumerate(osm):
        if p["ref"] in usados:
            descartados += 1
            continue
        tk = toks(p["nombre"])
        dup = False
        for q in puntos:
            if q["fuente"] != "direcciones.md":
                continue
            if hav(p["lat"], p["lon"], q["lat"], q["lon"]) < 40 and (tk & toks(q["nombre"])):
                dup = True
                break
        if dup:
            descartados += 1
            continue
        puntos.append({
            "id": "osm-%04d" % j,
            "nombre": p["nombre"],
            "direccion": p["direccion"],
            "colonia": p.get("colonia", ""),
            "cp": p.get("cp", ""),
            "lat": round(p["lat"], 6), "lon": round(p["lon"], 6),
            "sector": p.get("sector", "no_determinado"),
            "categoria": p.get("categoria", "servicios"),
            "zona": "",
            "precision": p.get("precision", "poi_exacto"),
            "verificacion": p.get("verificacion", "osm_poi"),
            "ref": p["ref"],
            "cotejo": p.get("origen_direccion", ""),
            "nota": p.get("operador", ""),
            "fuente": "OpenStreetMap",
        })

    zonas = cargar_zonas(rings)
    colonias = cargar_colonias(rings)

    # conteo de puntos por colonia (asignacion a la colonia mas cercana)
    for c in colonias:
        c["puntos"] = 0
    if colonias:
        for pt in puntos:
            k = min(range(len(colonias)),
                    key=lambda i: hav(pt["lat"], pt["lon"], colonias[i]["lat"], colonias[i]["lon"]))
            colonias[k]["puntos"] += 1

    area_muni_km2 = area_m2([(la, lo) for lo, la in rings[0]]) / 1e6
    area_hab_km2 = sum(z["area_ha"] for z in zonas) / 100.0

    meta = {
        "generado": __import__("datetime").date.today().isoformat(),
        "ciudad": "Xalapa-Enriquez, Veracruz, Mexico",
        "limite_municipal": "OSM relation/6037863",
        "poblacion_municipal_2020": POBLACION_CIUDAD,
        "area_municipal_km2": round(area_muni_km2, 1),
        "densidad_hab_km2": round(POBLACION_CIUDAD / area_muni_km2) if area_muni_km2 else None,
        "area_habitacional_km2": round(area_hab_km2, 2),
        "total_puntos": len(puntos),
        "del_listado": sum(1 for p in puntos if p["fuente"] == "direcciones.md"),
        "de_osm": sum(1 for p in puntos if p["fuente"] == "OpenStreetMap"),
        "duplicados_descartados": descartados,
        "zonas_habitacionales": len(zonas),
        "colonias": len(colonias),
        "por_sector": dict(Counter(p["sector"] for p in puntos)),
        "por_categoria": dict(Counter(p["categoria"] for p in puntos)),
        "por_precision": dict(Counter(p["precision"] for p in puntos)),
        "fuentes": ["direcciones.md (listado original)",
                    "OpenStreetMap / Overpass API",
                    "Nominatim (geocodificacion directa e inversa)"],
        "aviso_densidad": ("No existe poblacion por colonia en las fuentes usadas. "
                           "La densidad que muestra el mapa es de puntos de interes "
                           "por superficie, calculada con los datos reales cargados."),
    }

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "puntos": puntos, "zonas": zonas,
                   "colonias": colonias}, f, ensure_ascii=False)

    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
