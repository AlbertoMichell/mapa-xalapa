# -*- coding: utf-8 -*-
"""Descarga el poligono del municipio de Xalapa y expone punto-en-poligono.

Sirve de filtro duro: cualquier coordenada fuera del municipio se rechaza sin
depender de mas llamadas de red.
"""
import io, json, os, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "xalapa_boundary.json")
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}
EPS = ["https://overpass.kumi.systems/api/interpreter",
       "https://overpass.private.coffee/api/interpreter",
       "https://overpass.osm.jp/api/interpreter"]

# relation 6037863 = municipio de Xalapa (confirmada via Nominatim)
LOOKUP = ("https://nominatim.openstreetmap.org/lookup?" + urllib.parse.urlencode(
    {"osm_ids": "R6037863", "format": "json", "polygon_geojson": 1}))


def fetch():
    for _ in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(LOOKUP, headers=UA),
                                        timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print("   reintento boundary:", type(e).__name__)
            time.sleep(7)
    return None


def rings_from(geo):
    """Extrae los anillos exteriores de un Polygon o MultiPolygon GeoJSON."""
    t, coords = geo.get("type"), geo.get("coordinates") or []
    if t == "Polygon":
        polys = [coords]
    elif t == "MultiPolygon":
        polys = coords
    else:
        return []
    return [[(float(x), float(y)) for x, y in p[0]] for p in polys if p and len(p[0]) > 3]


def ensure():
    if os.path.exists(PATH) and os.path.getsize(PATH) > 500:
        return json.load(io.open(PATH, encoding="utf-8"))
    data = fetch()
    if not data:
        raise SystemExit("no se pudo descargar el limite municipal")
    rel = data[0]
    out = {"name": rel.get("display_name", "Xalapa"),
           "osm": "relation/%s" % rel.get("osm_id"),
           "rings": rings_from(rel.get("geojson") or {})}
    if not out["rings"]:
        raise SystemExit("la relacion no trajo poligono")
    with io.open(PATH, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def point_in(rings, lat, lon):
    for ring in rings:
        inside = False
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat):
                xint = xi + (lat - yi) * (xj - xi) / ((yj - yi) or 1e-12)
                if lon < xint:
                    inside = not inside
            j = i
        if inside:
            return True
    return False


if __name__ == "__main__":
    b = ensure()
    print(b["name"], b["osm"], "anillos:", len(b["rings"]),
          "vertices:", sum(len(r) for r in b["rings"]))
    for name, la, lo in (("centro", 19.5270, -96.9224),
                         ("Rafael Lucio", 19.5747, -96.9986),
                         ("Emiliano Zapata", 19.5077, -96.8610)):
        print("  %-16s dentro=%s" % (name, point_in(b["rings"], la, lo)))
