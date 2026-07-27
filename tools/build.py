# -*- coding: utf-8 -*-
"""Ejecuta el pipeline completo en orden. Todo es idempotente y usa cache."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASOS = ["parse_md.py", "osm_fetch.py", "zonas_fetch.py", "geocode.py",
         "resolve_pending.py", "interp_num.py", "verify.py", "enrich.py",
         "merge.py", "make_app.py"]


def main():
    solo = sys.argv[1:]
    for p in PASOS:
        if solo and p not in solo:
            continue
        if not os.path.exists(os.path.join(HERE, p)):
            print("== %-20s (aun no existe, se omite)" % p)
            continue
        print("\n" + "=" * 62)
        print("== %s" % p)
        print("=" * 62)
        r = subprocess.run([sys.executable, os.path.join(HERE, p)],
                           cwd=os.path.dirname(HERE))
        if r.returncode != 0:
            print("!! fallo en %s" % p)
            return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
