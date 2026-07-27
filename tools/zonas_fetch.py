# -*- coding: utf-8 -*-
"""Descarga la geometria de las zonas habitacionales y de las colonias.

La primera pasada de osm_fetch pidio 'out center', que solo trae el centroide.
Para dibujar poligonos en el mapa hace falta 'out geom'.
"""
import io, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "data", "osm")
BBOX = "19.4600,-97.0100,19.6100,-96.8300"
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}
EPS = ["https://overpass.kumi.systems/api/interpreter",
       "https://overpass.private.coffee/api/interpreter",
       "https://overpass.osm.jp/api/interpreter"]

CONSULTAS = {
    "habitacional_geom": '[out:json][timeout:120];'
                         'way["landuse"="residential"](%s);out geom tags;' % BBOX,
    "colonias_geom":     '[out:json][timeout:120];'
                         '(way["place"~"^(neighbourhood|suburb|quarter)$"](%s);'
                         'node["place"~"^(neighbourhood|suburb|quarter|town|city)$"](%s););'
                         'out geom tags;' % (BBOX, BBOX),
}


def run(q):
    for i in range(9):
        try:
            body = urllib.parse.urlencode({"data": q}).encode()
            with urllib.request.urlopen(urllib.request.Request(
                    EPS[i % len(EPS)], data=body, headers=UA), timeout=180) as r:
                txt = r.read().decode("utf-8", "replace")
            if txt.lstrip().startswith("{"):
                return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("   reintento (%s)\n" % type(e).__name__)
        time.sleep(8)
    return None


def main():
    for nombre, q in CONSULTAS.items():
        dest = os.path.join(OUTDIR, nombre + ".json")
        if os.path.exists(dest) and os.path.getsize(dest) > 500:
            print("[=] %s ya existe" % nombre)
            continue
        print("[>] %s ..." % nombre)
        d = run(q)
        if not d:
            print("[!] %s fallo" % nombre)
            continue
        with io.open(dest, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        print("[+] %s: %d elementos" % (nombre, len(d.get("elements", []))))
        time.sleep(4)


if __name__ == "__main__":
    main()
