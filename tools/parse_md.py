# -*- coding: utf-8 -*-
"""Extrae las entradas de direcciones.md a data/seed.json (deduplicado)."""
import json, os, re, io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "direcciones.md")
OUT = os.path.join(ROOT, "data", "seed.json")

ZONE_RE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ0-9\.\,\s/–\-()]+$")

def norm(s):
    return re.sub(r"\s+", " ", s).strip()

def main():
    raw = io.open(SRC, encoding="utf-8").read()
    # quitar cercas de bloque de codigo
    lines = [l for l in raw.split("\n") if l.strip() != "```"]

    # reunir lineas continuadas: una entrada arranca en la linea que contiene "—"
    # y sigue hasta la proxima linea que contenga "—" o sea encabezado de zona.
    entries, zone, buf, zbuf = [], None, None, None

    def flush():
        nonlocal buf
        if buf:
            entries.append((zone, norm(buf)))
            buf = None

    for line in lines:
        t = line.rstrip()
        if not t.strip():
            continue
        if "—" in t:
            flush()
            buf = t.strip()
        elif ZONE_RE.match(t.strip()) and "(" in t and "CP" in t:
            flush()
            zone = norm(t.strip())
        elif ZONE_RE.match(t.strip()) and len(t.strip()) > 6 and not buf:
            zone = norm(t.strip())
        elif buf:
            # continuacion de la entrada previa
            buf += " " + t.strip()
        else:
            zone = norm(t.strip())

    flush()

    recs, seen = [], set()
    for z, e in entries:
        # una linea puede traer pegado el inicio de un encabezado de zona
        if "—" not in e:
            continue
        head, tail = e.rsplit("—", 1)  # el ultimo guion largo separa el domicilio
        name, addr = norm(head), norm(tail)
        sector = "publica"
        for tag, val in ((" · privada", "privada"), (" · mixta", "mixta")):
            if addr.endswith(tag):
                addr, sector = norm(addr[: -len(tag)]), val
        # si el texto de la zona quedo pegado al final de la direccion, cortarlo
        addr = re.sub(r"\s*·?\s*(mixta|privada)?(ZONA CENTRO|EL MIRADOR|UNIDAD DEL BOSQUE|AV\. ÁVILA|COL\. REVOLUCIÓN|LOS ÁNGELES|LAS ÁNIMAS).*$", "", addr)
        addr = norm(addr)
        key = (name.lower(), addr.lower())
        if key in seen or not name:
            continue
        seen.add(key)
        recs.append({"nombre": name, "direccion": addr, "zona": z, "sector": sector,
                     "fuente": "direcciones.md"})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    print("entradas unicas:", len(recs))
    for r in recs:
        print(" -", r["sector"][:4], "|", r["nombre"][:52], "|", r["direccion"][:58])

if __name__ == "__main__":
    main()
