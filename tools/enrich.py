# -*- coding: utf-8 -*-
"""Convierte los POIs de OSM en registros con domicilio, colonia, CP y sector.

El domicilio sale de las etiquetas addr:* cuando existen y, si no, de la
geocodificacion inversa de la propia coordenada. El sector (publico/privado) se
deduce de etiquetas y de indicios en el nombre; cuando los indicios no alcanzan
se deja explicitamente como no_determinado en lugar de suponer.
"""
import io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OSMDIR = os.path.join(DATA, "osm")
OUT = os.path.join(DATA, "osm_pois.json")
RCACHE = os.path.join(DATA, "revcache.json")
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}
SALTAR = {"habitacional.json", "colonias.json", "direcciones_num.json"}

try:
    CACHE = json.load(io.open(RCACHE, encoding="utf-8"))
except Exception:  # noqa: BLE001
    CACHE = {}
_pend = [0]


def sa(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


def reverse(lat, lon):
    key = "%.6f,%.6f" % (lat, lon)
    if key in CACHE:
        return CACHE[key]
    url = ("https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1}))
    res = {}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=45) as r:
                res = json.loads(r.read().decode("utf-8"))
            break
        except Exception:  # noqa: BLE001
            time.sleep(5 + attempt * 5)
    CACHE[key] = res
    _pend[0] += 1
    if _pend[0] % 25 == 0:
        with io.open(RCACHE, "w", encoding="utf-8") as f:
            json.dump(CACHE, f, ensure_ascii=False)
    time.sleep(1.15)
    return res


# --------------------------------------------------------------- clasificacion
PUB = [r"\bgobierno\b", r"\bmunicipal\b", r"\bestatal\b", r"\bfederal\b",
       r"secretaria", r"\bimss\b", r"\bissste\b", r"\bdif\b", r"\bsat\b",
       r"\bine\b", r"\binegi\b", r"universidad veracruzana", r"\buv\b",
       r"centro de salud", r"hospital (general|regional|civil|escuela)",
       r"fiscalia", r"tribunal", r"juzgado", r"ayuntamiento", r"congreso",
       r"registro (civil|publico)", r"telesecundaria", r"conalep", r"cbtis",
       r"cecyte", r"cobaev", r"\bdgeti\b", r"instituto (nacional|mexicano|estatal)",
       r"comision (estatal|nacional)", r"procuraduria", r"delegacion",
       r"escuela (primaria|secundaria|telesecundaria)", r"jardin de ni",
       r"\bcbta\b", r"\bcam\b", r"\bcendi\b", r"seguridad publica",
       r"proteccion civil", r"casa de la cultura", r"biblioteca publica"]

PRIV = [r"\bbanco\b", r"\bbbva\b", r"banamex", r"santander", r"\bhsbc\b",
        r"banorte", r"scotiabank", r"banco azteca", r"bancoppel", r"\bafore\b",
        r"notaria", r"despacho", r"\bs\.?a\.?\s*de\s*c\.?v\.?", r"colegio",
        r"\bclinica\b", r"sanatorio", r"consultorio", r"aseguradora",
        r"inmobiliaria", r"corporativo", r"\bsucursal\b", r"universidad (anahuac|del valle|cristobal|mexicana|popular)",
        r"instituto (cultural|educativo|tecnologico de estudios superiores)"]

CAT_POR_ARCHIVO = {"gobierno": "gobierno", "justicia": "justicia",
                   "seguridad": "seguridad", "salud": "salud",
                   "educacion": "educacion", "financiero": "financiero",
                   "servicios": "servicios"}


def clasificar(tags, categoria):
    texto = sa("%s %s" % (tags.get("name", ""), tags.get("operator", "")))
    ot = (tags.get("operator:type") or "").lower()
    am, of = tags.get("amenity"), tags.get("office")

    pub = sum(1 for p in PUB if re.search(p, texto))
    priv = sum(1 for p in PRIV if re.search(p, texto))

    if ot in ("public", "government"):
        pub += 3
    if ot in ("private", "commercial"):
        priv += 3
    if of == "government" or tags.get("government") or \
            am in ("townhall", "courthouse", "police", "fire_station", "prison"):
        pub += 3
    if am == "bank" or of in ("notary", "lawyer", "company", "estate_agent",
                              "insurance", "financial"):
        priv += 3

    if pub and pub > priv:
        return "publica"
    if priv and priv > pub:
        return "privada"
    if pub and pub == priv:
        return "mixta"
    return "no_determinado"


def domicilio(tags, rev):
    """Prefiere las etiquetas addr:* del propio objeto; si no, la inversa."""
    calle, num = tags.get("addr:street"), tags.get("addr:housenumber")
    a = rev.get("address") or {}
    if not calle:
        calle, num = a.get("road"), num or a.get("house_number")
    partes = []
    if calle:
        partes.append("%s %s" % (calle, num) if num else calle)
    # Nominatim devuelve la colonia mexicana casi siempre como 'hamlet'
    col = (tags.get("addr:suburb") or tags.get("addr:neighbourhood") or
           a.get("neighbourhood") or a.get("suburb") or a.get("quarter") or
           a.get("residential") or a.get("hamlet") or "")
    if col:
        partes.append(col)
    cp = tags.get("addr:postcode") or a.get("postcode") or ""
    origen = "etiquetas OSM" if tags.get("addr:street") else "geocodificacion inversa"
    return ", ".join(partes) or "(sin domicilio cartografiado)", col, cp, origen


def main():
    rings = boundary.ensure()["rings"]
    vistos, recs = set(), []
    archivos = [f for f in sorted(os.listdir(OSMDIR))
                if f.endswith(".json") and f not in SALTAR]
    for fn in archivos:
        cat = CAT_POR_ARCHIVO.get(fn[:-5], "servicios")
        for el in json.load(io.open(os.path.join(OSMDIR, fn), encoding="utf-8"))["elements"]:
            t = el.get("tags") or {}
            if not t.get("name"):
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or not boundary.point_in(rings, lat, lon):
                continue
            ref = "%s/%s" % (el.get("type"), el.get("id"))
            if ref in vistos:
                continue
            vistos.add(ref)
            recs.append({"nombre": t["name"], "lat": lat, "lon": lon, "ref": ref,
                         "categoria": cat, "_tags": t})

    print("POIs unicos dentro del municipio:", len(recs))
    for i, r in enumerate(recs, 1):
        t = r.pop("_tags")
        rev = reverse(r["lat"], r["lon"]) if not t.get("addr:street") else {}
        dirc, col, cp, origen = domicilio(t, rev)
        r.update(direccion=dirc, colonia=col, cp=cp, origen_direccion=origen,
                 sector=clasificar(t, r["categoria"]),
                 tipo=t.get("amenity") or t.get("office") or t.get("healthcare") or "",
                 operador=t.get("operator", ""), fuente="OpenStreetMap",
                 precision="poi_exacto", verificacion="osm_poi")
        if i % 50 == 0:
            print("   %d/%d" % (i, len(recs)))

    with io.open(RCACHE, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print("\nsector:", dict(Counter(r["sector"] for r in recs)))
    print("categoria:", dict(Counter(r["categoria"] for r in recs)))
    print("con domicilio:", sum(1 for r in recs if not r["direccion"].startswith("(sin")))


if __name__ == "__main__":
    main()
