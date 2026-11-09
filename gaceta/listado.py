"""Lectura del índice de La Gaceta en enag.gob.hn (Joomla con EDocman).

Estructura comprobada el 9 de noviembre de 2026:
  /index.php/gaceta-digital                 años (12 por página, ?start=12)
  /index.php/gaceta-digital/<año>           meses
  /index.php/gaceta-digital/<año>/<mes>     ediciones, 5 por página (?start=5, 10...)
Cada edición: título "AAAAMMDD - número", tamaño, fecha de creación, sumario y enlace /download.
"""
import re
import urllib.parse

from crawler.dom import analizar, lineas, texto_unico

BASE = "https://enag.gob.hn"
INDICE = BASE + "/index.php/gaceta-digital"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def url_mes(anio, mes, inicio=0):
    u = f"{INDICE}/{anio}/{mes}"
    return u + (f"?start={inicio}" if inicio else "")


def parsear_ediciones(html: str) -> dict:
    """Devuelve {'ediciones': [...], 'siguientes': [offsets de paginación]}."""
    raiz = analizar(html)
    ediciones = []
    for d in raiz.buscar(clase="edocman-document"):
        t = d.primero(tag="a", clase="edocman-document-title-link")
        titulo = texto_unico(t.texto()) if t else ""
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})\s*-\s*(\d+)", titulo)
        descarga = next((a.get("href") for a in d.buscar(tag="a") if (a.get("href") or "").endswith("/download")), None)
        tam = d.primero(clase="sizeinformation")
        fec = d.primero(clase="dateinformation")
        desc = d.primero(clase="edocman-description-details")
        ediciones.append({
            "titulo": titulo,
            "fecha": f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None,
            "numero": int(m.group(4)) if m else None,
            "detalle": urllib.parse.urljoin(BASE, t.get("href")) if t is not None else None,
            "descarga": urllib.parse.urljoin(BASE, descarga) if descarga else None,
            "tamano": texto_unico(tam.texto()) if tam else None,
            "fecha_creacion": (re.search(r"(\d{2}-\d{2}-\d{4})", fec.texto()) or [None, None])[1] if fec else None,
            "sumario": lineas(desc.texto()) if desc else [],
        })
    siguientes = sorted({int(x) for x in re.findall(r"[?&]start=(\d+)", html)})
    return {"ediciones": ediciones, "siguientes": siguientes}


def tamano_mb(texto):
    """'3.42 MB' -> 3.42; '1.16 GB' -> 1187.84; None si no se puede leer."""
    m = re.match(r"([\d.,]+)\s*([KMG]B)", texto or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return {"KB": v / 1024, "MB": v, "GB": v * 1024}[m.group(2)]
