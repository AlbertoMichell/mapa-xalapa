# -*- coding: utf-8 -*-
"""Descarga POIs reales de OpenStreetMap para Xalapa via Overpass.

Cada categoria se guarda por separado en data/osm/<cat>.json para que un fallo
parcial no obligue a repetir todo. Se reintenta contra varios endpoints.
"""
import io, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "data", "osm")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]

BBOX = "19.4600,-97.0100,19.6100,-96.8300"  # S,W,N,E  Xalapa y conurbacion

# categoria -> lista de filtros de etiquetas OSM
CATS = {
    "gobierno":      ['["office"="government"]', '["amenity"="townhall"]',
                      '["government"]', '["office"="administrative"]'],
    "justicia":      ['["amenity"="courthouse"]', '["office"="notary"]',
                      '["office"="lawyer"]', '["amenity"="prison"]'],
    "seguridad":     ['["amenity"="police"]', '["amenity"="fire_station"]'],
    "salud":         ['["amenity"="hospital"]', '["amenity"="clinic"]',
                      '["amenity"="doctors"]', '["healthcare"="centre"]'],
    "educacion":     ['["amenity"="school"]', '["amenity"="university"]',
                      '["amenity"="college"]', '["amenity"="kindergarten"]'],
    "financiero":    ['["amenity"="bank"]', '["office"="insurance"]',
                      '["office"="financial"]'],
    "servicios":     ['["amenity"="post_office"]', '["amenity"="library"]',
                      '["office"="company"]', '["office"="estate_agent"]',
                      '["amenity"="community_centre"]'],
    "habitacional":  ['["landuse"="residential"]'],
    "colonias":      ['["place"~"^(neighbourhood|suburb|quarter|town|city)$"]'],
}


def build_query(filters, want_area=False):
    parts = []
    for f in filters:
        parts.append('node%s(%s);' % (f, BBOX))
        parts.append('way%s(%s);' % (f, BBOX))
        parts.append('relation%s(%s);' % (f, BBOX))
    out = "out center tags;" if not want_area else "out center tags;"
    return "[out:json][timeout:90];(%s);%s" % ("".join(parts), out)


def run(query, tries=len(ENDPOINTS) * 2):
    last = ""
    for i in range(tries):
        url = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            body = urllib.parse.urlencode({"data": query}).encode()
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode("utf-8", "replace")
            if txt.lstrip().startswith("{"):
                return json.loads(txt)
            last = txt[:200].replace("\n", " ")
        except Exception as e:  # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
        sys.stderr.write("  reintento %d (%s) -> %s\n" % (i + 1, url.split("/")[2], last[:120]))
        time.sleep(8 + i * 4)
    return None


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    only = sys.argv[1:] or list(CATS)
    for cat in only:
        dest = os.path.join(OUTDIR, cat + ".json")
        if os.path.exists(dest) and os.path.getsize(dest) > 200:
            n = len(json.load(io.open(dest, encoding="utf-8")).get("elements", []))
            print("[=] %-13s ya descargado (%d elementos)" % (cat, n))
            continue
        print("[>] %-13s descargando..." % cat)
        data = run(build_query(CATS[cat]))
        if data is None:
            print("[!] %-13s FALLO" % cat)
            continue
        with io.open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print("[+] %-13s %d elementos" % (cat, len(data.get("elements", []))))
        time.sleep(3)


if __name__ == "__main__":
    main()
