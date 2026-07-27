# -*- coding: utf-8 -*-
"""Geocodifica data/seed.json.

Orden de resolucion (de mas a menos confiable):
  1. Coincidencia por nombre contra los POIs de OSM ya descargados (data/osm).
  2. Nominatim con varias variantes de consulta.
Todo resultado queda registrado con su fuente y su osm_id para poder auditarlo.
Nunca se inventan coordenadas: si nada resuelve, el registro queda sin_coordenada.
"""
import io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE_PATH = os.path.join(DATA, "geocache.json")

# recuadro de Xalapa: todo resultado fuera de aqui se descarta
S, W, N, E = 19.46, -97.02, 19.62, -96.82
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}

STOP = set("de del la las los el y en al a con por para no s/n esq oficina piso planta "
           "sede modulo local km col av avenida calle c gral dependencia estatal".split())


def strip_acc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def toks(s):
    s = strip_acc(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return set(w for w in s.split() if len(w) > 2 and w not in STOP)


def in_box(lat, lon):
    return S <= lat <= N and W <= lon <= E


# ---------------------------------------------------------------- cache
try:
    CACHE = json.load(io.open(CACHE_PATH, encoding="utf-8"))
except Exception:  # noqa: BLE001
    CACHE = {}


def save_cache():
    with io.open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False)


# ---------------------------------------------------------------- nominatim
_last = [0.0]


def nominatim(q):
    if q in CACHE:
        return CACHE[q]
    wait = 1.2 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    url = ("https://nominatim.openstreetmap.org/search?" +
           urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 5,
                                   "addressdetails": 1, "countrycodes": "mx",
                                   "viewbox": "%f,%f,%f,%f" % (W, N, E, S),
                                   "bounded": 1}))
    res = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=45) as r:
                res = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("   nominatim fallo (%s), reintento\n" % type(e).__name__)
            time.sleep(5 + attempt * 5)
    _last[0] = time.time()
    CACHE[q] = res
    save_cache()
    return res


# ---------------------------------------------------------------- POIs OSM
def load_osm_pois():
    pois = []
    d = os.path.join(DATA, "osm")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn in ("habitacional.json", "colonias.json") or not fn.endswith(".json"):
            continue
        blob = json.load(io.open(os.path.join(d, fn), encoding="utf-8"))
        for el in blob.get("elements", []):
            t = el.get("tags") or {}
            name = t.get("name")
            if not name:
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or not in_box(lat, lon):
                continue
            pois.append({"name": name, "lat": lat, "lon": lon, "tags": t,
                         "osm": "%s/%s" % (el.get("type"), el.get("id")),
                         "tk": toks(name)})
    return pois


def build_idf(pois):
    """Frecuencia documental de cada palabra dentro del corpus de nombres OSM."""
    import math
    df = {}
    for p in pois:
        for t in p["tk"]:
            df[t] = df.get(t, 0) + 1
    n = float(len(pois)) or 1.0
    return df, {t: math.log(n / c) for t, c in df.items()}


def match_osm(rec, pois, df, idf):
    """Coincidencia por nombre ponderada por rareza de las palabras.

    Solo se consideran las palabras del registro que existen en el corpus OSM:
    las que no aparecen en ningun nombre no pueden coincidir y penalizarlas
    impediria reconocer siglas como ORFIS o SEFIPLAN.
    """
    want = toks(rec["nombre"])
    posibles = {t for t in want if t in idf}
    if not posibles:
        return None
    denom = sum(idf[t] for t in posibles) or 1e-9

    best, best_score = None, 0.0
    for p in pois:
        inter = posibles & p["tk"]
        if not inter:
            continue
        cover = sum(idf[t] for t in inter) / denom
        # el nombre del POI tambien debe quedar razonablemente explicado
        pdenom = sum(idf.get(t, 0.0) for t in p["tk"]) or 1e-9
        pcover = sum(idf[t] for t in inter) / pdenom
        distintivo = any(df[t] <= 4 for t in inter) or len(inter) >= 2
        if cover >= 0.60 and pcover >= 0.35 and distintivo:
            score = (cover + pcover) / 2.0
            if score > best_score:
                best, best_score = p, score
    if best:
        return best, best_score
    return None


# ---------------------------------------------------------------- clasificacion
def precision_of(hit):
    at = hit.get("addresstype") or hit.get("type") or ""
    cls = hit.get("class") or ""
    addr = hit.get("address") or {}
    if cls in ("office", "amenity", "shop", "healthcare", "tourism", "leisure") \
            or at in ("office", "amenity"):
        return "poi_exacto"
    if addr.get("house_number"):
        return "numero_exacto"
    if at in ("road", "highway") or cls == "highway":
        return "calle"
    return "aproximada"


def variants(rec):
    nom, dirc = rec["nombre"], rec["direccion"]
    out = []
    if nom and not nom.lower().startswith("dependencia"):
        out.append("%s, Xalapa, Veracruz" % nom)
        if dirc:
            out.append("%s, %s, Xalapa, Veracruz" % (nom, dirc))
    if dirc:
        out.append("%s, Xalapa, Veracruz" % dirc)
        # calle + numero, sin colonia ni piso
        m = re.match(r"^([^,0-9]+?)\s*(\d{1,4})\b", dirc)
        if m:
            out.append("%s %s, Xalapa, Veracruz" % (m.group(1).strip(), m.group(2)))
        base = re.split(r",", dirc)[0]
        if base and base != dirc:
            out.append("%s, Xalapa, Veracruz" % base.strip())
    seen, uniq = set(), []
    for v in out:
        if v.lower() not in seen:
            seen.add(v.lower())
            uniq.append(v)
    return uniq


def calle_tokens(direccion):
    """Palabras de la vialidad: lo que va antes de la primera coma o numero."""
    base = re.split(r"[,0-9]", direccion)[0]
    return toks(base)


def por_direccion(rec, rings):
    """Geocodifica usando el domicilio, no el nombre. Filtra por el municipio."""
    for q in variants(rec):
        for h in nominatim(q):
            lat, lon = float(h["lat"]), float(h["lon"])
            if in_box(lat, lon) and boundary.point_in(rings, lat, lon):
                return {"lat": lat, "lon": lon, "precision": precision_of(h),
                        "verificacion": "nominatim", "consulta": q,
                        "ref": "%s/%s" % (h.get("osm_type"), h.get("osm_id")),
                        "match": h.get("display_name"), "confianza": None}
    return None


def main():
    seed = json.load(io.open(os.path.join(DATA, "seed.json"), encoding="utf-8"))
    rings = boundary.ensure()["rings"]
    pois = [p for p in load_osm_pois() if boundary.point_in(rings, p["lat"], p["lon"])]
    df, idf = build_idf(pois)
    print("POIs OSM dentro del municipio de Xalapa:", len(pois))

    # --- paso 1: coincidencia por nombre, solo como candidata
    cand = [None] * len(seed)
    for i, rec in enumerate(seed):
        m = match_osm(rec, pois, df, idf)
        if not m:
            continue
        p, sc = m
        # Si el nombre coincide con fuerza se acepta tal cual: un inmueble en
        # esquina suele registrar en OSM una vialidad distinta a la citada.
        # Con coincidencia intermedia se exige ademas que la vialidad concuerde.
        via = p["tags"].get("addr:street")
        if sc < 0.75 and via and calle_tokens(rec["direccion"]) \
                and not (toks(via) & calle_tokens(rec["direccion"])):
            continue
        cand[i] = (p, sc)

    # --- paso 2: un mismo inmueble no puede ser dos registros distintos
    porref = {}
    for i, c in enumerate(cand):
        if c:
            porref.setdefault(c[0]["osm"], []).append(i)
    for ref, idxs in porref.items():
        if len(idxs) < 2:
            continue
        idxs.sort(key=lambda i: cand[i][1], reverse=True)
        for i in idxs[1:]:
            print("    colision en %s -> se reasigna '%s' por domicilio"
                  % (ref, seed[i]["nombre"][:40]))
            cand[i] = None

    # --- paso 3: resolucion final
    out, sin = [], 0
    for i, rec in enumerate(seed, 1):
        r = dict(rec)
        c = cand[i - 1]
        if c:
            p, sc = c
            r.update(lat=p["lat"], lon=p["lon"], precision="poi_exacto",
                     verificacion="osm_poi", ref=p["osm"], match=p["name"],
                     confianza=round(sc, 2))
        else:
            hit = por_direccion(rec, rings)
            if hit:
                r.update(**hit)
            else:
                r.update(lat=None, lon=None, precision="sin_coordenada",
                         verificacion="no_resuelto")
                sin += 1
        out.append(r)
        print("%3d/%d %-14s %s" % (i, len(seed), r["precision"], r["nombre"][:46]))

    with io.open(os.path.join(DATA, "seed_geo.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nsin coordenada:", sin, "de", len(out))


if __name__ == "__main__":
    main()
