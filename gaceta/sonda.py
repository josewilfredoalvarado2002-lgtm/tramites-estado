"""Sonda de La Gaceta: comprueba el acceso desde GitHub y mide cómo sale el texto de los PDF.

No escribe notas. Descarga una edición de varios años, extrae el texto con dos métodos y guarda
en gaceta_sonda/ el texto, los datos de cada PDF y un resumen, para diseñar la separación de normas
sobre texto real. Los PDF no se guardan en el repositorio.

Uso:  python3 -m gaceta.sonda
Requiere: poppler-utils (pdftotext, pdfinfo, pdffonts) y el paquete pymupdf.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from .listado import parsear_ediciones, tamano_mb, url_mes

AGENTE = "CaseDeck-Normativa/0.1 (sonda; consulta de La Gaceta digital)"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "gaceta_sonda")
PAUSA = 3.0
MAX_MB = 60
# (año, mes, edición buscada o None para la primera del mes)
MUESTRAS = [(2011, "enero", None), (2015, "enero", None), (2018, "enero", None), (2020, "enero", None),
            (2023, "enero", None), (2026, "octubre", 37261), (2026, "octubre", 37262)]


def pedir(url, binario=False, limite_mb=None):
    time.sleep(PAUSA)
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=120) as r:
        if not binario:
            return r.read().decode("utf-8", errors="replace")
        datos, limite = bytearray(), (limite_mb or MAX_MB) * 1024 * 1024
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            datos += trozo
            if len(datos) > limite:
                raise ValueError(f"el PDF pasa de {limite_mb or MAX_MB} MB")
        return bytes(datos)


def texto_columnas(pagina):
    """Texto de una página a dos columnas: bloques de ancho completo en su lugar y, entre ellos,
    primero la columna izquierda y luego la derecha."""
    ancho = pagina.rect.width
    mitad = ancho / 2
    bloques = [b for b in pagina.get_text("blocks") if b[6] == 0 and b[4].strip()]
    anchos = [b for b in bloques if b[0] < mitad - 20 and b[2] > mitad + 20]
    resto = [b for b in bloques if b not in anchos]
    izq = [b for b in resto if (b[0] + b[2]) / 2 < mitad]
    der = [b for b in resto if (b[0] + b[2]) / 2 >= mitad]
    salida, desde = [], -1.0
    for corte in sorted(anchos, key=lambda b: b[1]) + [None]:
        hasta = corte[1] if corte else 1e9
        for col in (izq, der):
            salida += [b[4].strip() for b in sorted(col, key=lambda b: b[1]) if desde <= b[1] < hasta]
        if corte:
            salida.append(corte[4].strip())
            desde = corte[3]
    return "\n".join(salida)


def analizar_pdf(ruta, carpeta):
    try:
        import pymupdf as fitz
    except ImportError:  # versiones anteriores de pymupdf
        import fitz
    info = {}
    try:
        info["pdfinfo"] = subprocess.run(["pdfinfo", ruta], capture_output=True, text=True, timeout=60).stdout
        fuentes = subprocess.run(["pdffonts", ruta], capture_output=True, text=True, timeout=60).stdout.splitlines()
        info["fuentes"] = max(0, len(fuentes) - 2)
        subprocess.run(["pdftotext", "-layout", ruta, os.path.join(carpeta, "pdftotext_layout.txt")], timeout=300)
    except FileNotFoundError:
        info["poppler"] = "no instalado"
    doc = fitz.open(ruta)
    paginas, sin_texto, encabezados = [], [], []
    for i, p in enumerate(doc, 1):
        t = texto_columnas(p)
        crudo = p.get_text()
        if len(crudo.strip()) < 50:
            sin_texto.append(i)
        lin = [x for x in crudo.splitlines() if x.strip()]
        encabezados.append({"pagina": i, "primeras": lin[:4], "ultimas": lin[-3:], "imagenes": len(p.get_images())})
        paginas.append(f"\n===== Página {i} =====\n{t}")
    with open(os.path.join(carpeta, "pymupdf_columnas.txt"), "w", encoding="utf-8") as f:
        f.write("".join(paginas))
    info.update({"paginas": len(doc), "paginas_sin_texto": sin_texto, "encabezados": encabezados})
    return info


def main():
    os.makedirs(os.path.join(SALIDA, "listados"), exist_ok=True)
    resumen = []
    for anio, mes, buscada in MUESTRAS:
        url = url_mes(anio, mes)
        fila = {"muestra": f"{anio} {mes}", "listado": url}
        try:
            html = pedir(url)
            with open(os.path.join(SALIDA, "listados", f"{anio}-{mes}.html"), "w", encoding="utf-8") as f:
                f.write(html)
            datos = parsear_ediciones(html)
            ediciones = datos["ediciones"]
            fila["ediciones_en_pagina"] = len(ediciones)
            fila["paginacion"] = datos["siguientes"]
            ed = next((e for e in ediciones if buscada is None or e["numero"] == buscada), None)
            if ed is None and buscada:
                for inicio in datos["siguientes"]:
                    ed = next((e for e in parsear_ediciones(pedir(url_mes(anio, mes, inicio)))["ediciones"]
                               if e["numero"] == buscada), None)
                    if ed:
                        break
            if ed is None:
                raise ValueError("no se encontró la edición")
            fila.update({"edicion": ed["titulo"], "tamano": ed["tamano"], "sumario": ed["sumario"]})
            if (tamano_mb(ed["tamano"]) or 0) > MAX_MB:
                raise ValueError(f"edición de {ed['tamano']}, se omite en la sonda")
            pdf = pedir(ed["descarga"], binario=True)
            carpeta = os.path.join(SALIDA, re.sub(r"\W+", "_", ed["titulo"]).strip("_"))
            os.makedirs(carpeta, exist_ok=True)
            ruta = os.path.join("/tmp", os.path.basename(carpeta) + ".pdf")
            with open(ruta, "wb") as f:
                f.write(pdf)
            info = analizar_pdf(ruta, carpeta)
            info["edicion"] = ed
            with open(os.path.join(carpeta, "info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=1)
            fila.update({"mb": round(len(pdf) / 1e6, 2), "paginas": info["paginas"], "fuentes": info.get("fuentes"),
                         "paginas_sin_texto": len(info["paginas_sin_texto"]), "resultado": "OK"})
        except Exception as e:  # noqa: BLE001
            fila["resultado"] = f"ERROR {type(e).__name__}: {e}"
        print(json.dumps({k: v for k, v in fila.items() if k != "sumario"}, ensure_ascii=False), flush=True)
        resumen.append(fila)
    with open(os.path.join(SALIDA, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)
    errores = [r for r in resumen if not str(r.get("resultado", "")).startswith("OK")]
    print("Resultado:", "La Gaceta responde desde aquí" if len(errores) < len(resumen) else "no se pudo leer ninguna edición")
    return 0 if len(errores) < len(resumen) else 2


if __name__ == "__main__":
    sys.exit(main())
