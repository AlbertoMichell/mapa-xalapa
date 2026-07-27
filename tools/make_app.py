# -*- coding: utf-8 -*-
"""Incrusta dataset.json dentro de la plantilla y produce el archivo unico."""
import io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boundary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "tools", "app_template.html")
SRC = os.path.join(ROOT, "data", "dataset.json")
OUT = os.path.join(ROOT, "mapa_xalapa.html")


def main():
    datos = json.load(io.open(SRC, encoding="utf-8"))

    # el limite municipal se simplifica: un vertice de cada cuatro basta para dibujarlo
    anillo = boundary.ensure()["rings"][0]
    datos["limite"] = [[round(la, 5), round(lo, 5)] for lo, la in anillo[::4]]

    tpl = io.open(TPL, encoding="utf-8").read()
    # el JSON va dentro de <script type="application/json">: hay que neutralizar
    # cualquier secuencia que cierre el elemento antes de tiempo
    blob = json.dumps(datos, ensure_ascii=False, separators=(",", ":")) \
        .replace("</", "<\\/")
    html = tpl.replace("/*__DATOS__*/", blob)
    if "/*__DATOS__*/" in html or blob not in html:
        raise SystemExit("no se pudo incrustar el dataset en la plantilla")

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("generado: %s (%.1f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))
    print("puntos incrustados:", len(datos["puntos"]))


if __name__ == "__main__":
    main()
