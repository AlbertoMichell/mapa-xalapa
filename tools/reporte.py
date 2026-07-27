# -*- coding: utf-8 -*-
"""Resumen de procedencia y calidad del dataset final."""
import io, json, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

NIVEL = {"poi_exacto": "inmueble localizado en OSM",
         "numero_exacto": "numero oficial levantado en campo",
         "numero_interpolado": "interpolado entre numeros levantados",
         "numero_cercano": "numero mas cercano levantado",
         "edificio_compartido": "mismo inmueble que otra oficina",
         "cruce_calles": "cruce de vialidades",
         "calle": "nivel de vialidad",
         "colonia": "nivel de colonia",
         "aproximada": "aproximada"}


def main():
    d = json.load(io.open(os.path.join(DATA, "dataset.json"), encoding="utf-8"))
    rings = boundary.ensure()["rings"]
    pts, meta = d["puntos"], d["meta"]

    fuera = [p for p in pts if not boundary.point_in(rings, p["lat"], p["lon"])]
    sin_ref = [p for p in pts if not p["ref"]]
    sin_dir = [p for p in pts if not p["direccion"] or p["direccion"].startswith("(sin")]

    print("=" * 66)
    print(" DATASET DE DIRECCIONES  ·  %s" % meta["ciudad"])
    print("=" * 66)
    print(" Total de direcciones ........ %d" % len(pts))
    print("   del listado direcciones.md  %d" % meta["del_listado"])
    print("   de OpenStreetMap .......... %d" % meta["de_osm"])
    print("   duplicados descartados .... %d" % meta["duplicados_descartados"])
    print()
    print(" CONTROLES SUPERADOS")
    print("   dentro del municipio ...... %d / %d" % (len(pts) - len(fuera), len(pts)))
    print("   con identificador OSM ..... %d / %d" % (len(pts) - len(sin_ref), len(pts)))
    print("   con domicilio ............. %d / %d" % (len(pts) - len(sin_dir), len(pts)))
    print()
    print(" PRECISION DE LA UBICACION")
    for k, n in Counter(p["precision"] for p in pts).most_common():
        print("   %-22s %4d   %s" % (k, n, NIVEL.get(k, "")))
    print()
    print(" NATURALEZA DE LA OFICINA")
    for k, n in Counter(p["sector"] for p in pts).most_common():
        print("   %-22s %4d" % (k, n))
    print()
    print(" CATEGORIA")
    for k, n in Counter(p["categoria"] for p in pts).most_common():
        print("   %-22s %4d" % (k, n))
    print()
    print(" CONTEXTO TERRITORIAL")
    print("   superficie municipal ...... %s km2" % meta["area_municipal_km2"])
    print("   poblacion 2020 (INEGI) .... %s" % format(meta["poblacion_municipal_2020"], ",d"))
    print("   densidad .................. %s hab/km2" % format(meta["densidad_hab_km2"], ",d"))
    print("   zonas habitacionales ...... %d (%s km2)" % (meta["zonas_habitacionales"],
                                                          meta["area_habitacional_km2"]))
    print("   colonias con poligono ..... %d" % meta["colonias"])
    print()

    seed = json.load(io.open(os.path.join(DATA, "seed_geo.json"), encoding="utf-8"))
    est = Counter((r.get("control") or {}).get("estado", "?") for r in seed)
    print(" LISTADO ORIGINAL (direcciones.md): %d registros" % len(seed))
    print("   sin observaciones ......... %d" % est.get("ok", 0))
    print("   con aviso ................. %d" % est.get("aviso", 0))
    print("   con error ................. %d" % est.get("error", 0))
    if fuera:
        print("\n !! %d punto(s) fuera del municipio:" % len(fuera))
        for p in fuera[:10]:
            print("    -", p["nombre"][:60])
    print("=" * 66)


if __name__ == "__main__":
    main()
