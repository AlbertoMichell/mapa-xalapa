# -*- coding: utf-8 -*-
"""Resuelve los registros que quedaron sin coordenada en seed_geo.json.

Metodos, todos verificables y sin inventar coordenadas:
  osm    -> objeto OSM concreto (relation/way/node) consultado por id
  cruce  -> nodo real de interseccion entre dos vialidades nombradas en OSM
  igual  -> mismo inmueble que otro registro ya resuelto (edificios compartidos)
  query  -> consulta dirigida a Nominatim, con la direccion confirmada por fuente
"""
import io, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PATH = os.path.join(DATA, "seed_geo.json")
BBOX = "19.4600,-97.0100,19.6100,-96.8300"
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}
ENDPOINTS = ["https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter",
             "https://overpass.osm.jp/api/interpreter"]

# indice en seed_geo.json -> como resolverlo
PLAN = {
    0:  {"osm": ("relation", 19247480),
         "nota": "Palacio de Gobierno, relacion OSM confirmada por Nominatim"},
    15: {"cruce": ("Leandro Valle", "Ignacio Zaragoza"),
         "nota": "cruce de vialidades declarado en la direccion"},
    27: {"osm": ("way", 184843026), "prec": "calle",
         "nota": "unica via 'Cultura Veracruzana' cartografiada en Xalapa; el numero 120 no esta en OSM"},
    30: {"cruce": ("Adolfo Ruiz Cortines", "Avenida Xalapa"),
         "nota": "cruce de vialidades declarado en la direccion"},
    31: {"query": "Avenida Xalapa 279, Xalapa, Veracruz",
         "nota": "Av. Jalapa 279, Unidad del Bosque"},
    44: {"igual": 43,
         "nota": "'mismo edificio': Torre Orgullo Veracruzano, Av. Lazaro Cardenas 1104"},
    51: {"igual": 47,
         "nota": "OIC de la Contraloria General, mismo inmueble de Ignacio de la Llave 105"},
    64: {"query": "ORFIS, Xalapa, Veracruz", "prec": "poi_exacto",
         "nota": "POI 'ORFIS' en OSM; orfis.gob.mx declara Carr. Xalapa-Veracruz 1102 esq. Blvd. Culturas Veracruzanas, CP 91096"},
    66: {"query": "Reserva Territorial, Xalapa, Veracruz", "prec": "colonia",
         "nota": "cespver.gob.mx: Blvd. Rafael Guizar y Valencia s/n, Col. Reserva Territorial; el circuito no esta cartografiado"},
    69: {"query": "Indeco Animas, Xalapa, Veracruz", "prec": "colonia",
         "nota": "bienestar.gob.mx: Carr. Xalapa-Veracruz Km 0+700, Col. Indeco Animas, CP 91196"},
    59: {"query": "Avenida 20 de Noviembre Oriente, Xalapa, Veracruz", "prec": "calle",
         "nota": "la busqueda por nombre generico caia en otra colonia; se ancla a la vialidad"},
    63: {"igual": 62, "prec": "edificio_compartido",
         "nota": "Col. SAHOP esta en el Km 4.5 de la carretera Xalapa-Veracruz, sede de la SEV"},
}

# indices que se recalculan aunque ya tengan coordenada (correcciones dirigidas)
FORZAR = {59, 63}


def overpass(q):
    for i in range(len(ENDPOINTS) * 2):
        url = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            body = urllib.parse.urlencode({"data": q}).encode()
            with urllib.request.urlopen(
                    urllib.request.Request(url, data=body, headers=UA), timeout=120) as r:
                txt = r.read().decode("utf-8", "replace")
            if txt.lstrip().startswith("{"):
                return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("   overpass %s: %s\n" % (url.split("/")[2], type(e).__name__))
        time.sleep(6)
    return None


def by_id(kind, oid):
    d = overpass("[out:json][timeout:60];%s(%d);out center tags;" % (kind, oid))
    els = (d or {}).get("elements") or []
    if not els:
        return None
    el = els[0]
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    if lat is None:
        return None
    return lat, lon, "%s/%s" % (kind, oid), (el.get("tags") or {}).get("name", "")


def crossing(a, b):
    """Nodo compartido entre dos vialidades nombradas: interseccion real."""
    q = ('[out:json][timeout:90];'
         'way["name"~"%s",i](%s);node(w)->.a;'
         'way["name"~"%s",i](%s);node(w)->.b;'
         'node.a.b;out %s;' % (a, BBOX, b, BBOX, "1"))
    d = overpass(q)
    els = (d or {}).get("elements") or []
    if not els:
        return None
    el = els[0]
    return el["lat"], el["lon"], "node/%s" % el["id"], "cruce %s / %s" % (a, b)


def nominatim(q):
    url = ("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "mx",
         "viewbox": "-97.02,19.62,-96.82,19.46", "bounded": 1}))
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=45) as r:
                res = json.loads(r.read().decode("utf-8"))
            if res:
                h = res[0]
                return (float(h["lat"]), float(h["lon"]),
                        "%s/%s" % (h.get("osm_type"), h.get("osm_id")),
                        h.get("display_name", ""))
            return None
        except Exception:  # noqa: BLE001
            time.sleep(5)
    return None


def main():
    recs = json.load(io.open(PATH, encoding="utf-8"))
    ok = 0
    for idx, plan in sorted(PLAN.items()):
        r = recs[idx]
        if r.get("lat") is not None and idx not in FORZAR:
            continue
        res, metodo, prec = None, "", ""
        if "osm" in plan:
            res, metodo = by_id(*plan["osm"]), "osm_objeto"
            prec = plan.get("prec", "poi_exacto")
        elif "cruce" in plan:
            res, metodo, prec = crossing(*plan["cruce"]), "osm_cruce", "cruce_calles"
            if res is None:  # sin nodo compartido, se cae a la vialidad principal
                res = nominatim("%s, Xalapa, Veracruz" % plan["cruce"][0])
                metodo, prec = "nominatim", "calle"
        elif "igual" in plan:
            src = recs[plan["igual"]]
            if src.get("lat") is not None:
                res = (src["lat"], src["lon"], src.get("ref", ""), src["nombre"])
                metodo = "edificio_compartido"
                prec = plan.get("prec", "edificio_compartido")
        elif "query" in plan:
            res, metodo = nominatim(plan["query"]), "nominatim"
            prec = plan.get("prec", "calle")

        if res:
            lat, lon, ref, match = res
            r.update(lat=lat, lon=lon, precision=prec, verificacion=metodo,
                     ref=ref, match=match, nota=plan["nota"])
            ok += 1
            print("[+] %2d %-22s %-18s %.5f, %.5f  %s" %
                  (idx, metodo, prec, lat, lon, r["nombre"][:34]))
        else:
            print("[!] %2d NO RESUELTO  %s" % (idx, r["nombre"][:50]))

    with io.open(PATH, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    falta = sum(1 for r in recs if r.get("lat") is None)
    print("\nresueltos ahora: %d | sin coordenada restantes: %d de %d" % (ok, falta, len(recs)))


if __name__ == "__main__":
    main()
