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


def _paquete_certificados():
    """Raíces de certifi + certificados intermedios que algunos sitios oficiales no envían
    (su servidor manda solo el certificado final; macOS lo completa solo, Linux no)."""
    import tempfile
    import certifi
    extra = os.path.join(_AQUI, "certificados_intermedios.pem")
    if not os.path.exists(extra):
        return True
    ruta = os.path.join(tempfile.gettempdir(), "certificados_sitios.pem")
    with open(ruta, "w") as f:
        f.write(open(certifi.where()).read() + "\n" + open(extra).read())
    return ruta


class Cliente:
    def __init__(self, permitidos, pausa=1.5, js=False):
        # js: False, True, o el selector CSS que hay que esperar a que aparezca (portales que cargan después)
        self.js = js            # True: las páginas se abren en un navegador (sitios que arman el contenido con JavaScript)
        self._nav = None
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
        ultimo, verificar = None, True
        for intento in range(1, 4):
            try:
                try:
                    r = self.s.get(url, timeout=60, verify=verificar)
                except requests.exceptions.SSLError:
                    if verificar is not True:
                        raise
                    # cadena de certificados incompleta: se reintenta con los intermedios conocidos (sigue verificando)
                    verificar = _paquete_certificados()
                    r = self.s.get(url, timeout=60, verify=verificar)
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

    def _navegador(self):
        if self._nav is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._nav = self._pw.chromium.launch()
            self._pag = self._nav.new_page(user_agent=UA)
        return self._pag

    def cerrar(self):
        if self._nav is not None:
            self._nav.close()
            self._pw.stop()
            self._nav = None

    def sopa_js(self, url, espera=4000):
        if not self.permitido(url):
            self.rechazadas.append(url)
            raise DominioNoVerificado(f"fuera de los dominios verificados: {url}")
        pag = self._navegador()
        ultimo = None
        for intento in range(1, 4):
            try:
                pag.goto(url, timeout=90000, wait_until="networkidle")
                if isinstance(self.js, str):
                    pag.wait_for_selector(self.js, timeout=60000)
                pag.wait_for_timeout(espera)
                # tablas paginadas (DataTables): se muestran todas las filas
                pag.evaluate("""() => { try { if (window.jQuery && jQuery.fn.dataTable)
                    jQuery('table.dataTable').each(function(){ jQuery(this).DataTable().page.len(-1).draw(); }); } catch(e) {} }""")
                pag.wait_for_timeout(500)
                if not self.permitido(pag.url):
                    self.rechazadas.append(pag.url)
                    raise DominioNoVerificado(f"{url} redirigió fuera de los dominios verificados: {pag.url}")
                html = pag.content()
                time.sleep(self.pausa)
                return BeautifulSoup(html, "html.parser"), pag.url
            except DominioNoVerificado:
                raise
            except Exception as e:
                ultimo = type(e).__name__
                time.sleep(4 * intento)
        raise RuntimeError(f"No se pudo abrir {url} en el navegador ({ultimo})")

    def sopa(self, url):
        if self.js:
            return self.sopa_js(url)
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
        return json.dumps({"v": 2, "t": self.titulo, "c": self.categoria, "a": self.actualizado_fuente,
                           "s": self.secciones, "d": [(d["nombre"], d["url"].split("?")[0]) for d in self.documentos]},
                          ensure_ascii=False, sort_keys=True)

    # ---- análisis: para qué se hace, requisitos, formulario
    def para_que(self):
        from estructura import para_que_de_pagina
        return para_que_de_pagina(self.secciones, self.titulo)

    def tiene_requisitos(self):
        from estructura import tiene_requisitos_pagina
        return tiene_requisitos_pagina(self.secciones)

    def solo_formulario(self):
        """Todo lo que hay es un formulario para llenar (o la ficha es de tipo formato)."""
        docs = [d for d in self.documentos if d.get("texto")]
        if self.tipo == "formato":
            return True
        return bool(docs) and all(d.get("formulario") for d in docs) and not any(
            not k.startswith(("Para qué", "Requisitos", "Costo", "Plazo", "Dónde", "Base legal", "Procedimiento",
                              "Notas", "Otro texto", "Documento")) for k in self.secciones)

    def relevante(self):
        """Se guarda si trae requisitos; si no, solo si explica un trámite y no es un formulario.
        Un documento ilegible se guarda solo si su título dice que es de requisitos."""
        if self.tiene_requisitos():
            return True
        if self.solo_formulario():
            return False
        if self.para_que():
            return True
        ilegible = any(not d.get("texto") and re.search(r"OCR|escaneado|imagen", d.get("aviso", "")) for d in self.documentos)
        if re.search(r"requisit", self.titulo, re.I) and (ilegible or not self.secciones):
            return True
        return False

    def calidad(self):
        if not self.secciones:
            return "sin_contenido"
        req, para = self.tiene_requisitos(), bool(self.para_que())
        if req and para:
            return "completo"
        if req:
            return "solo_requisitos"
        if para:
            return "solo_para_que"
        return "sin_requisitos"


# --------------------------------------------------------------- documentos
def texto_pdf(contenido):
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(contenido))
    return "\f".join((p.extract_text() or "") for p in pdf.pages)


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
    elif datos[:3] == b"\xff\xd8\xff" or datos[:8] == b"\x89PNG\r\n\x1a\n":
        ocr = texto_ocr_imagen(datos)
        if ocr:
            return ocr, ("texto leído por OCR (el sitio lo publica como imagen): puede tener errores de lectura; "
                         "compará con la imagen antes de usarlo")
        return "", "el sitio lo publica como imagen: hay que abrirla a mano"
    else:
        return "", "el enlace no entregó un PDF ni un Word"
    t = "\f".join("\n".join(limpiar(l) for l in p.splitlines()) for p in t.split("\f"))
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(re.sub(r"\s", "", t)) < 80:
        if datos[:4] == b"%PDF":
            ocr = texto_ocr(datos)
            if ocr:
                return ocr, ("texto leído por OCR (el PDF es una imagen escaneada): puede tener errores de lectura; "
                             "compará con el PDF antes de usarlo")
        return "", "PDF escaneado o sin texto: hay que abrirlo a mano"
    return t, ""


def texto_ocr_imagen(datos):
    import shutil
    import subprocess
    if not shutil.which("tesseract"):
        return ""
    try:
        r = subprocess.run(["tesseract", "stdin", "-", "-l", "spa"], input=datos, timeout=120, capture_output=True)
        t = "\n".join(limpiar(l) for l in r.stdout.decode("utf-8", "ignore").splitlines())
    except Exception:
        return ""
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t if len(re.sub(r"\s", "", t)) >= 80 else ""


def texto_ocr(datos, paginas=8):
    """OCR en español con tesseract, solo si está instalado (en GitHub Actions sí). Máximo 8 páginas."""
    import shutil
    import subprocess
    import tempfile
    if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        return ""
    with tempfile.TemporaryDirectory() as d:
        pdf = os.path.join(d, "doc.pdf")
        open(pdf, "wb").write(datos)
        try:
            subprocess.run(["pdftoppm", "-r", "200", "-l", str(paginas), "-png", pdf, os.path.join(d, "p")],
                           check=True, timeout=180, capture_output=True)
            textos = []
            for img in sorted(f for f in os.listdir(d) if f.endswith(".png")):
                r = subprocess.run(["tesseract", os.path.join(d, img), "-", "-l", "spa"], timeout=120,
                                   capture_output=True, text=True)
                textos.append("\n".join(limpiar(l) for l in r.stdout.splitlines()))
        except Exception:
            return ""
    t = re.sub(r"\n{3,}", "\n\n", "\f".join(textos)).strip()
    return t if len(re.sub(r"\s", "", t)) >= 80 else ""
