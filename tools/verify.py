# -*- coding: utf-8 -*-
"""Comprueba cada coordenada de seed_geo.json contra la geocodificacion inversa.

Contrasta municipio, codigo postal, colonia y vialidad declarados en la
direccion original con lo que devuelve OSM para ese punto. Escribe el
resultado en el propio registro (campo 'control') y lista lo que hay que revisar.
"""
import io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PATH = os.path.join(DATA, "seed_geo.json")
RCACHE = os.path.join(DATA, "revcache.json")
UA = {"User-Agent": "XalapaCivicMap/1.0 (albertomichellh@gmail.com)"}

try:
    CACHE = json.load(io.open(RCACHE, encoding="utf-8"))
except Exception:  # noqa: BLE001
    CACHE = {}


def strip_acc(s):
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
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("   reverse fallo (%s)\n" % type(e).__name__)
            time.sleep(5 + attempt * 5)
    CACHE[key] = res
    with io.open(RCACHE, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False)
    time.sleep(1.2)
    return res


def main():
    recs = json.load(io.open(PATH, encoding="utf-8"))
    rings = boundary.ensure()["rings"]
    errores, avisos = [], []

    def inmueble(r):
        """Vialidad + numero declarados: identifica el inmueble, no la oficina."""
        d = strip_acc(r["direccion"])
        num = re.search(r"\b(\d{1,4})\b", d)
        via = re.split(r"[,0-9]", d)[0].strip()
        return (via, num.group(1) if num else "")

    vistos = {}
    for i, r in enumerate(recs):
        if r.get("lat") is None:
            errores.append((i, r, ["sin coordenada"]))
            continue
        rev = reverse(r["lat"], r["lon"])
        a = rev.get("address") or {}
        # Nominatim devuelve la colonia mexicana casi siempre como 'hamlet'
        colonia = (a.get("neighbourhood") or a.get("suburb") or a.get("quarter") or
                   a.get("residential") or a.get("hamlet") or a.get("village") or "")
        cp = a.get("postcode") or ""
        via = a.get("road") or ""
        muni = a.get("city") or a.get("town") or a.get("municipality") or ""

        err, avi = [], []
        if not boundary.point_in(rings, r["lat"], r["lon"]):
            err.append("fuera del municipio de Xalapa (%s)" % (muni or "?"))

        key = "%.5f,%.5f" % (r["lat"], r["lon"])
        if key in vistos:
            j = vistos[key]
            otro = recs[j]
            va, na = inmueble(r)
            vb, nb = inmueble(otro)
            contiguos = (va == vb and na and nb and abs(int(na) - int(nb)) <= 10)
            mismo_inmueble = (r.get("verificacion") == "edificio_compartido"
                              or (va, na) == (vb, nb) or contiguos)
            if mismo_inmueble:
                r["comparte_con"] = j
                avi.append("mismo inmueble que #%d (%s)" % (j, otro["nombre"][:28]))
            else:
                # direcciones distintas cayeron en el mismo punto de la vialidad
                err.append("punto compartido con #%d (%s) sin ser el mismo inmueble"
                           % (j, otro["nombre"][:28]))
        vistos.setdefault(key, i)

        cps = re.findall(r"\b(91\d{3})\b", strip_acc(r["direccion"] + " " + r.get("zona", "")))
        if cps and cp and cp not in cps:
            avi.append("CP OSM %s vs %s declarado" % (cp, "/".join(sorted(set(cps)))))
        if r.get("precision") in ("colonia", "aproximada"):
            avi.append("ubicacion a nivel %s" % r["precision"])

        r["control"] = {"municipio": muni, "colonia": colonia, "cp": cp, "via": via,
                        "direccion_osm": rev.get("display_name", ""),
                        "estado": "error" if err else ("aviso" if avi else "ok"),
                        "errores": err, "avisos": avi}
        if err:
            errores.append((i, r, err))
        elif avi:
            avisos.append((i, r, avi))

    with io.open(PATH, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)

    ok = sum(1 for r in recs if r.get("control", {}).get("estado") == "ok")
    print("=== %d registros: %d ok | %d con aviso | %d con error ===\n"
          % (len(recs), ok, len(avisos), len(errores)))
    for titulo, grupo in (("ERRORES", errores), ("AVISOS", avisos)):
        if not grupo:
            continue
        print("----- %s -----" % titulo)
        for i, r, m in grupo:
            print("%3d %-40s %s" % (i, r["nombre"][:40], "; ".join(m)))
            print("     decl: %-52s | osm: %s"
                  % (r["direccion"][:52], (r.get("control") or {}).get("direccion_osm", "")[:60]))
        print()


if __name__ == "__main__":
    main()
