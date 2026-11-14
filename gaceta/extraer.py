"""Crawler de La Gaceta digital (ENAG): baja ediciones, separa los actos de la Sección A y escribe
las notas en "11 Normativa". Va de la edición más reciente hacia atrás, por tandas.

Uso:  python3 -m gaceta.extraer --modo tanda [--max 40]
      python3 -m gaceta.extraer --modo piloto        (ediciones 37261 y 37262 de octubre de 2026)
Los PDF no se guardan. El avance queda en estado/gaceta.json. Requiere el paquete pymupdf.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
from zoneinfo import ZoneInfo

from . import reparar as R
from . import texto as T
from .listado import MESES, parsear_ediciones, tamano_mb, url_mes
from .sonda import pedir, texto_columnas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTADO = os.path.join(RAIZ, "estado", "gaceta.json")
CONFIG = os.path.join(RAIZ, "gaceta", "config.json")
VERSION = 2  # al subirla, las ediciones cargadas con una versión anterior se vuelven a leer
POR_DEFECTO = {"anio_minimo": 2020, "max_mb": 200, "max_por_tanda": 40, "minutos_maximos": 100, "intentos": 3}


def cargar(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir(rel, contenido):
    ruta = os.path.join(RAIZ, *rel.split("/"))
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenido)


def borrar_anteriores(previo, nuevas):
    """Al releer una edición quita del repositorio las notas de acto que ya no se generan."""
    viejas = set(previo.get("notas") or [])
    if not viejas and previo.get("ruta"):
        try:
            with open(os.path.join(RAIZ, *previo["ruta"].split("/")), encoding="utf-8") as f:
                viejas = {m + ".md" for m in re.findall(r"\[\[(11 Normativa/[^\]|\\]+)", f.read()) if "/La Gaceta/" not in m and "Índice" not in m}
        except OSError:
            pass
    for rel in viejas - set(nuevas):
        ruta = os.path.join(RAIZ, *rel.split("/"))
        if rel.startswith(T.CARPETA + "/") and ".." not in rel and os.path.isfile(ruta):
            os.remove(ruta)


def ediciones_del_mes(anio, mes):
    """Todas las ediciones del mes (todas las páginas del listado). None si el mes no existe."""
    try:
        datos = parsear_ediciones(pedir(url_mes(anio, mes)))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    eds, vistos = list(datos["ediciones"]), {0}
    pendientes = list(datos["siguientes"])
    while pendientes:
        ini = pendientes.pop(0)
        if ini in vistos:
            continue
        vistos.add(ini)
        d = parsear_ediciones(pedir(url_mes(anio, mes, ini)))
        eds += d["ediciones"]
        pendientes += [x for x in d["siguientes"] if x not in vistos]
    unicas = {e["numero"]: e for e in eds if e["numero"] and e["descarga"] and e["fecha"]}
    return sorted(unicas.values(), key=lambda e: (e["fecha"], e["numero"]), reverse=True)


def procesar(ed, cfg, hoy, previo=None):
    """Devuelve el registro de la edición para el estado."""
    reg = {"fecha": ed["fecha"], "tamano": ed["tamano"]}
    mb = tamano_mb(ed["tamano"]) or 0
    if mb > cfg["max_mb"]:
        return {**reg, "resultado": "omitida", "motivo": f"pesa {ed['tamano']} (límite {cfg['max_mb']} MB)"}
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    pdf = pedir(ed["descarga"], binario=True, limite_mb=cfg["max_mb"] + 10)
    doc = fitz.open(stream=pdf, filetype="pdf")
    paginas = [texto_columnas(p) for p in doc]
    sin_texto = sum(1 for t in paginas if len(t.strip()) < 50)
    renglones, resumen = T.limpiar_paginas(paginas)
    actos = T.separar_actos(renglones, ed.get("sumario"))
    usadas, rutas = set(), []
    for a in actos:
        ruta = T.ruta_acto(ed, a, usadas)
        escribir(ruta, R.reparar_nota(T.nota_acto(ed, a, hoy), cfg.get("_voc", frozenset())))
        rutas.append(ruta)
    borrar_anteriores(previo or {}, rutas)
    ruta_ed = T.ruta_edicion(ed)
    escribir(ruta_ed, R.reparar_nota(T.nota_edicion(ed, actos, rutas, resumen, hoy), frozenset()))
    reg.update({"resultado": "ok", "version": VERSION, "notas": rutas, "ruta": ruta_ed, "actos": len(actos), "paginas": len(paginas),
                "paginas_a": resumen["paginas_a"], "paginas_sin_texto": sin_texto, "extraido": hoy})
    if sin_texto > len(paginas) / 2:
        reg["aviso"] = "la mayoría de las páginas no trae texto (haría falta OCR)"
    return reg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["tanda", "piloto"], default="tanda")
    ap.add_argument("--max", type=int, default=0)
    args = ap.parse_args()
    cfg = {**POR_DEFECTO, **cargar(CONFIG, {})}
    cfg["_voc"] = R.vocabulario_repo(RAIZ)  # palabras ya escritas en la colección, para unir guiones
    estado = cargar(ESTADO, {"version": 1, "ediciones": {}, "meses_completos": []})
    hechas, completos = estado["ediciones"], set(estado["meses_completos"])
    ahora = dt.datetime.now(ZoneInfo("America/Tegucigalpa"))
    hoy, inicio = ahora.date().isoformat(), time.time()
    tope = args.max or cfg["max_por_tanda"]
    for r in hechas.values():  # ediciones leídas con una versión anterior: se repiten
        if r.get("resultado") == "ok" and r.get("version", 1) < VERSION:
            completos.discard(r["fecha"][:7])
    if args.modo == "piloto":
        meses, solo = [(2026, 10)], {37261, 37262}
    else:
        meses, solo = [], None
        a, m = ahora.year, ahora.month
        while a >= cfg["anio_minimo"]:
            meses.append((a, m))
            a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    n = errores = 0
    for anio, mes in meses:
        clave = f"{anio}-{mes:02d}"
        if n >= tope or time.time() - inicio > cfg["minutos_maximos"] * 60:
            break
        if clave in completos and not solo:
            continue
        try:
            eds = ediciones_del_mes(anio, MESES[mes - 1])
        except Exception as e:  # noqa: BLE001
            print(f"AVISO no se pudo leer el listado de {clave}: {type(e).__name__}: {e}", flush=True)
            errores += 1
            continue
        if eds is None:
            print(f"{clave}: el mes no existe en el portal", flush=True)
            eds = []
        falta = False
        for ed in eds:
            previo = hechas.get(str(ed["numero"])) or {}
            if solo is not None and ed["numero"] not in solo:
                continue
            if solo is None and ((previo.get("resultado") == "ok" and previo.get("version", 1) >= VERSION) or previo.get("resultado") == "omitida" or previo.get("intentos", 0) >= cfg["intentos"]):
                continue
            if n >= tope or time.time() - inicio > cfg["minutos_maximos"] * 60:
                falta = True
                break
            n += 1
            try:
                reg = procesar(ed, cfg, hoy, previo)
            except Exception as e:  # noqa: BLE001
                reg = {"fecha": ed["fecha"], "resultado": "error", "motivo": f"{type(e).__name__}: {e}"[:300],
                       "intentos": previo.get("intentos", 0) + 1,
                       **{k: previo[k] for k in ("ruta", "notas") if k in previo}}
                errores += 1
                falta = True
            hechas[str(ed["numero"])] = reg
            print(json.dumps({"edicion": ed["titulo"], **{k: v for k, v in reg.items() if k != "ruta"}}, ensure_ascii=False), flush=True)
        anterior = (ahora.year, ahora.month - 1) if ahora.month > 1 else (ahora.year - 1, 12)
        if eds and not falta and solo is None and (anio, mes) < anterior:
            completos.add(clave)
    estado["meses_completos"] = sorted(completos)
    estado["ultima_corrida"] = ahora.strftime("%Y-%m-%d %H:%M")
    escribir("estado/gaceta.json", json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True))
    listas = [(r["fecha"], int(num), r["ruta"], r.get("actos", 0)) for num, r in hechas.items() if r.get("resultado") == "ok"]
    for ruta, contenido in T.notas_indice(listas).items():
        escribir(ruta, contenido)
    ok = sum(1 for r in hechas.values() if r.get("resultado") == "ok")
    print(f"Resultado: {n} ediciones procesadas en esta corrida ({errores} con error). En total van {ok} ediciones cargadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
