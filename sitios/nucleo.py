"""
Piezas comunes: cliente HTTP con candado de dominio, modelo de ficha, lectura de PDF y DOCX.

Candado de dominio: solo se lee de los dominios que el Registro de instituciones marcó como
verificados para esa institución (más los secundarios oficiales). Si una URL o una redirección
sale de esos dominios, se rechaza y queda en la bitácora. Así un dominio abandonado o un enlace
a un tercero nunca termina copiado como si fuera oficial.
"""
import hashlib
import io
import json
import os
import re
import time
import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

warnings.filterwarnings("ignore")
import requests
from bs4 import BeautifulSoup

_AQUI = os.path.dirname(os.path.abspath(__file__))
# Registro de dominios verificados (Fase 0). En el repositorio va junto al código; en la Mac, en ~/crawlers/instituciones.
REGISTRO = os.environ.get("REGISTRO_INSTITUCIONES") or next(
    (r for r in (os.path.join(_AQUI, "registro.json"), os.path.expanduser("~/crawlers/instituciones/registro.json"))
     if os.path.exists(r)), os.path.join(_AQUI, "registro.json"))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def limpiar(t):
    return re.sub(r"[ \t\xa0]+", " ", (t or "")).strip()


def base(host):
    p = (host or "").lower().split(".")
    if len(p) >= 3 and ".".join(p[-2:]) in ("gob.hn", "edu.hn", "org.hn", "com.hn"):
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def huella(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class DominioNoVerificado(Exception):
    pass


def dominios_verificados(siglas):
    """Dominios permitidos para la institución según el Registro de instituciones."""
    datos = json.load(open(REGISTRO, encoding="utf-8"))
    for r in datos["instituciones"]:
        if r["siglas"] == siglas:
            if not r["estado"].startswith("verificado"):
                raise DominioNoVerificado(f"{siglas}: el sitio no está verificado ({r['estado']})")
            permitidos = {r["mejor"]["dominio_final"]}
            permitidos |= {p.get("dominio_final") for p in r["pruebas"] if p.get("rol") == "secundario oficial"}
            return {d for d in permitidos if d}, r
    raise DominioNoVerificado(f"{siglas} no está en el Registro de instituciones")


class Cliente:
    def __init__(self, permitidos, pausa=1.5):
        self.permitidos = set(permitidos)
        self.pausa = pausa
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.rechazadas = []

    def permitido(self, url):
        return base(urlparse(url).hostname) in self.permitidos

    def get(self, url, binario=False):
        if not self.permitido(url):
            self.rechazadas.append(url)
            raise DominioNoVerificado(f"fuera de los dominios verificados: {url}")
        ultimo = None
        for intento in range(1, 4):
            try:
                r = self.s.get(url, timeout=60)
                if not self.permitido(r.url):
                    self.rechazadas.append(r.url)
                    raise DominioNoVerificado(f"{url} redirigió fuera de los dominios verificados: {r.url}")
                if r.status_code == 200:
                    time.sleep(self.pausa)
                    return r
                ultimo = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                ultimo = type(e).__name__
            time.sleep(4 * intento)
        raise RuntimeError(f"No se pudo leer {url} ({ultimo})")

    def sopa(self, url):
        r = self.get(url)
        if "charset" not in r.headers.get("content-type", "").lower():
            r.encoding = r.apparent_encoding
        return BeautifulSoup(re.sub(r"</\s*br\s*>", "<br/>", r.text, flags=re.I), "html.parser"), r.url


@dataclass
class Ficha:
    siglas: str
    id_local: str              # identificador estable dentro del sitio (id de WordPress, etc.)
    titulo: str
    url_ficha: str
    tipo: str = "tramite"      # tramite | formato
    categoria: str = ""
    actualizado_fuente: str = ""   # fecha que el propio sitio publica
    secciones: dict = field(default_factory=dict)   # encabezado -> texto, en el orden del sitio
    documentos: list = field(default_factory=list)  # [{nombre, url, texto_extraido}]
    avisos: list = field(default_factory=list)

    def contenido(self):
        """Lo que se compara entre corridas (sin fechas de extracción)."""
        return json.dumps({"t": self.titulo, "c": self.categoria, "a": self.actualizado_fuente,
                           "s": self.secciones, "d": [(d["nombre"], d["url"].split("?")[0]) for d in self.documentos]},
                          ensure_ascii=False, sort_keys=True)

    def calidad(self):
        texto = " ".join(self.secciones.keys()).lower() + " " + " ".join(self.secciones.values()).lower()
        req = "requisit" in texto
        desc = any(k in " ".join(self.secciones.keys()).lower()
                   for k in ("descrip", "qué es", "que es", "objetivo", "para qué", "definici"))
        if not self.secciones:
            return "sin_contenido"
        if self.tipo == "formato":
            return "formato_con_texto"
        if req and desc:
            return "completo"
        if req:
            return "solo_requisitos"
        return "sin_requisitos"


# --------------------------------------------------------------- documentos
def texto_pdf(contenido):
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(contenido))
    return "\n".join((p.extract_text() or "") for p in pdf.pages)


def texto_docx(contenido):
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def texto_documento(cli, url):
    """Descarga un PDF/DOCX del dominio verificado y devuelve (texto, aviso)."""
    r = cli.get(url)
    datos = r.content
    if datos[:4] == b"%PDF":
        t = texto_pdf(datos)
    elif datos[:2] == b"PK":
        try:
            t = texto_docx(datos)
        except Exception:
            return "", "documento comprimido que no es Word: no se leyó"
    else:
        return "", "el enlace no entregó un PDF ni un Word"
    t = "\n".join(limpiar(l) for l in t.splitlines())
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) < 80:
        return "", "PDF escaneado o sin texto: hay que abrirlo a mano (no se usa OCR para no inventar)"
    return t, ""
