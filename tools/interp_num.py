# -*- coding: utf-8 -*-
"""Afina las ubicaciones a nivel de calle interpolando por numero oficial.

OSM tiene domicilios con numero levantados en campo. Para un registro con
vialidad y numero, se buscan los domicilios de esa misma vialidad, se ordenan
por numero y se interpola entre los dos que lo encierran. Es una posicion
derivada de mediciones reales, no una invencion: se marca como tal.
"""
import io, json, math, os, re, sys, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ADDR = os.path.join(DATA, "osm", "direcciones_num.json")
SEED = os.path.join(DATA, "seed_geo.json")
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}
EPS = ["https://overpass.kumi.systems/api/interpreter",
       "https://overpass.private.coffee/api/interpreter",
       "https://overpass.osm.jp/api/interpreter"]

# palabras genericas de vialidad que no distinguen una calle de otra
GEN = set("avenida av calle c blvd boulevard calzada carretera carr circuito "
          "privada priv prolongacion andador callejon paseo de del la las los y "
          "norte sur oriente poniente nte ote pte gral general lic ing dr".split())


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def via_key(s):
    """Palabras distintivas del nombre de una vialidad."""
    s = strip_acc(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return frozenset(w for w in s.split() if w not in GEN and len(w) > 2)


def num_of(s):
    d = "".join(c for c in (s or "") if c.isdigit())
    return int(d) if d else None


def haversine(la1, lo1, la2, lo2):
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def fetch_addresses():
    if os.path.exists(ADDR) and os.path.getsize(ADDR) > 500:
        return json.load(io.open(ADDR, encoding="utf-8"))
    q = ('[out:json][timeout:120];'
         'nwr["addr:housenumber"]["addr:street"](19.46,-97.01,19.61,-96.83);'
         'out center tags;')
    for i in range(9):
        try:
            body = urllib.parse.urlencode({"data": q}).encode()
            with urllib.request.urlopen(urllib.request.Request(
                    EPS[i % len(EPS)], data=body, headers=UA), timeout=180) as r:
                txt = r.read().decode("utf-8", "replace")
            if txt.lstrip().startswith("{"):
                d = json.loads(txt)
                with io.open(ADDR, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False)
                return d
        except Exception as e:  # noqa: BLE001
            print("   reintento direcciones:", type(e).__name__)
        time.sleep(7)
    raise SystemExit("no se pudieron descargar los domicilios con numero")


def build_index(blob, rings):
    """vialidad -> lista ordenada de (numero, lat, lon, nombre)."""
    idx = {}
    for el in blob.get("elements", []):
        t = el.get("tags") or {}
        n = num_of(t.get("addr:housenumber"))
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if n is None or lat is None or not boundary.point_in(rings, lat, lon):
            continue
        k = via_key(t.get("addr:street"))
        if not k:
            continue
        idx.setdefault(k, []).append((n, lat, lon, t.get("name", "")))
    for k in idx:
        idx[k].sort(key=lambda x: x[0])
    return idx


def buscar(idx, via_txt, numero):
    """Devuelve (lat, lon, metodo, detalle) o None."""
    k = via_key(via_txt)
    if not k:
        return None
    # la vialidad del registro debe quedar contenida en la del indice o al reves
    mejor, mejor_n = None, 0
    for kk, pts in idx.items():
        inter = k & kk
        if not inter:
            continue
        if len(inter) == len(k) or len(inter) == len(kk):
            if len(inter) > mejor_n:
                mejor, mejor_n = pts, len(inter)
    if not mejor or len(mejor) < 2:
        return None

    nums = [p[0] for p in mejor]
    if numero < nums[0] or numero > nums[-1]:
        # fuera del tramo levantado: se usa el extremo mas cercano solo si esta
        # razonablemente proximo en numeracion
        p = mejor[0] if numero < nums[0] else mejor[-1]
        if abs(numero - p[0]) > 120:
            return None
        return p[1], p[2], "numero_cercano", "extremo levantado no. %d" % p[0]

    lo = max([p for p in mejor if p[0] <= numero], key=lambda p: p[0])
    hi = min([p for p in mejor if p[0] >= numero], key=lambda p: p[0])
    if lo[0] == hi[0]:
        return lo[1], lo[2], "numero_exacto", "domicilio levantado no. %d" % lo[0]

    # En una vialidad larga y curva, interpolar en linea recta entre dos
    # domicilios distantes deja el punto fuera de la calle. Si el tramo es
    # amplio se prefiere el extremo mas cercano en numeracion.
    if haversine(lo[1], lo[2], hi[1], hi[2]) > 600:
        p = lo if (numero - lo[0]) <= (hi[0] - numero) else hi
        return p[1], p[2], "numero_cercano", "domicilio levantado no. %d" % p[0]

    t = (numero - lo[0]) / float(hi[0] - lo[0])
    return (lo[1] + (hi[1] - lo[1]) * t, lo[2] + (hi[2] - lo[2]) * t,
            "numero_interpolado", "entre no. %d y no. %d" % (lo[0], hi[0]))


def main():
    rings = boundary.ensure()["rings"]
    idx = build_index(fetch_addresses(), rings)
    print("vialidades con numeracion levantada:", len(idx))

    recs = json.load(io.open(SEED, encoding="utf-8"))
    mejorados = 0
    for i, r in enumerate(recs):
        # solo se afina lo que hoy esta a nivel de calle o peor
        if r.get("precision") not in ("calle", "aproximada", "cruce_calles", "colonia"):
            continue
        d = r["direccion"]
        m = re.match(r"^\s*([^,0-9]+?)\s+(\d{1,4})\b", d)
        if not m:
            continue
        via, numero = m.group(1), int(m.group(2))
        # "Km 4.5", "Km 0+700" son referencias kilometricas, no numeros oficiales
        if numero == 0 or re.search(r"\bkm\.?\s*$", strip_acc(via)):
            continue
        res = buscar(idx, via, numero)
        if not res:
            continue
        lat, lon, metodo, detalle = res
        if not boundary.point_in(rings, lat, lon):
            continue
        r.update(lat=round(lat, 7), lon=round(lon, 7), precision=metodo,
                 verificacion="osm_numeracion",
                 match="%s %d — %s" % (via.strip(), numero, detalle))
        mejorados += 1
        print("  [%2d] %-38s %-18s %s" % (i, r["nombre"][:38], metodo, detalle))

    with io.open(SEED, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    print("\nregistros afinados por numeracion:", mejorados)


if __name__ == "__main__":
    main()
