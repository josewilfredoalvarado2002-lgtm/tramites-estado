"""Acceso al Portal de Trámites del Estado de Honduras y lectura de sus páginas.

El portal entrega el listado y las fichas como HTML generado en el servidor
(no hay una API en JSON para las fichas), así que basta con peticiones HTTP
normales y un lector de HTML. No se usa navegador.
"""
import json
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from .dom import analizar, correo_cloudflare, lineas, texto_unico

BASE = "https://tramites.diger.gob.hn"
URL_LISTADO = BASE + "/tramites"
URL_FICHA = BASE + "/landingPage/DetalleTramite/{id}"

AGENTE = "CaseDeck-Tramites/1.0 (consulta mensual de fichas publicas del portal; uso interno de consulta)"
NO_CONSTA = "No consta en el portal"


class BloqueoDelSitio(Exception):
    """El sitio respondió con una verificación o bloqueo (por ejemplo, Cloudflare). No se intenta saltarlo."""


class FichaInvalida(Exception):
    """La página no tiene la estructura de una ficha."""


class Respuesta:
    def __init__(self, estado, url_final, texto, cabeceras):
        self.estado = estado
        self.url_final = url_final
        self.texto = texto
        self.cabeceras = cabeceras


class Cliente:
    """Cliente HTTP respetuoso: pausa entre peticiones, reintentos con espera y agente identificable."""

    def __init__(self, pausa=2.5, reintentos=3, espera_base=10, timeout=30, agente=AGENTE, registro=None):
        self.pausa = pausa
        self.reintentos = reintentos
        self.espera_base = espera_base
        self.timeout = timeout
        self.agente = agente
        self._ultima = 0.0
        self.peticiones = 0
        self.registro = registro or (lambda msg: None)
        self._cache_final = {}

    def _esperar_turno(self):
        falta = self.pausa + random.uniform(0, 1.0) - (time.monotonic() - self._ultima)
        if falta > 0:
            time.sleep(falta)
        self._ultima = time.monotonic()

    def _abrir(self, url, metodo="GET", datos=None, cabeceras=None):
        h = {"User-Agent": self.agente, "Accept": "text/html,application/xhtml+xml",
             "Accept-Language": "es-HN,es;q=0.9"}
        h.update(cabeceras or {})
        req = urllib.request.Request(url, data=datos, headers=h, method=metodo)
        return urllib.request.urlopen(req, timeout=self.timeout)

    def obtener(self, url, aceptar_404=True) -> Respuesta:
        ultimo_error = None
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            self.peticiones += 1
            try:
                with self._abrir(url) as r:
                    cuerpo = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
                    return Respuesta(r.status, r.geturl(), cuerpo, dict(r.headers))
            except urllib.error.HTTPError as e:
                cuerpo = ""
                try:
                    cuerpo = e.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
                if e.code == 404 and aceptar_404:
                    return Respuesta(404, url, cuerpo, dict(e.headers or {}))
                if e.code in (403, 503) and _parece_verificacion(cuerpo, e.headers):
                    raise BloqueoDelSitio(f"{url} respondió {e.code} con una verificación del sitio") from e
                if e.code == 429 or e.code >= 500:
                    ultimo_error = f"HTTP {e.code}"
                    espera = _retry_after(e.headers) or self.espera_base * (3 ** (intento - 1))
                    self.registro(f"Reintento {intento}/{self.reintentos} de {url} en {espera:.0f} s ({ultimo_error})")
                    if intento < self.reintentos:
                        time.sleep(min(espera, 300))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                ultimo_error = str(getattr(e, "reason", e))
                espera = self.espera_base * (3 ** (intento - 1))
                self.registro(f"Reintento {intento}/{self.reintentos} de {url} en {espera:.0f} s ({ultimo_error})")
                if intento < self.reintentos:
                    time.sleep(espera)
        raise ConnectionError(f"No se pudo obtener {url} después de {self.reintentos} intentos: {ultimo_error}")

    def enviar_json(self, url, datos):
        """POST con cuerpo JSON (lo usa el comparador del portal). Mismas pausas y reintentos que obtener()."""
        cuerpo = json.dumps(datos).encode("utf-8")
        ultimo_error = None
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            self.peticiones += 1
            try:
                with self._abrir(url, "POST", cuerpo, {"Content-Type": "application/json",
                                                       "Accept": "application/json"}) as r:
                    return json.loads(r.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                texto = ""
                try:
                    texto = e.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
                if e.code in (403, 503) and _parece_verificacion(texto, e.headers):
                    raise BloqueoDelSitio(f"{url} respondió {e.code} con una verificación del sitio") from e
                if e.code == 429 or e.code >= 500:
                    ultimo_error = f"HTTP {e.code}"
                    if intento < self.reintentos:
                        time.sleep(min(_retry_after(e.headers) or self.espera_base * (3 ** (intento - 1)), 300))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
                ultimo_error = str(getattr(e, "reason", e))
                if intento < self.reintentos:
                    time.sleep(self.espera_base * (3 ** (intento - 1)))
        raise ConnectionError(f"No se pudo consultar {url} después de {self.reintentos} intentos: {ultimo_error}")

    def resolver_url_final(self, url):
        """Sigue las redirecciones del botón de acción (sitio de la institución).
        Devuelve (url_final, error). No reintenta ni descarga el contenido."""
        if not url:
            return None, None
        if url in self._cache_final:
            return self._cache_final[url]
        fragmento = urllib.parse.urlsplit(url).fragment
        resultado = (None, None)
        try:
            time.sleep(1.0)
            self.peticiones += 1
            with self._abrir(url, cabeceras={"Accept": "*/*"}) as r:
                final = r.geturl()
        except urllib.error.HTTPError as e:
            # el servidor respondió; la URL a la que llegó sigue siendo la final
            final = e.geturl() or url
        except Exception as e:  # noqa: BLE001
            resultado = (None, f"{type(e).__name__}: {getattr(e, 'reason', e)}")
            self._cache_final[url] = resultado
            return resultado
        if _sin_fragmento(final) == _sin_fragmento(url):
            final = url
        elif fragmento and not urllib.parse.urlsplit(final).fragment:
            # comportamiento de los navegadores: el fragmento se conserva tras una redirección
            final = final + "#" + fragmento
        resultado = (final, None)
        self._cache_final[url] = resultado
        return resultado


def _sin_fragmento(u):
    return urllib.parse.urldefrag(u)[0]


def _retry_after(cabeceras):
    try:
        return float((cabeceras or {}).get("Retry-After"))
    except (TypeError, ValueError):
        return None


def _parece_verificacion(cuerpo, cabeceras):
    if (cabeceras or {}).get("cf-mitigated"):
        return True
    c = (cuerpo or "")[:20000]
    return "<main" not in c and any(s in c for s in ("Just a moment", "cf-challenge", "Attention Required", "challenge-platform"))


# ---------------------------------------------------------------------------
# Comparador del portal ("Comparar trámites"): acepta entre 2 y 3 trámites por consulta
# ---------------------------------------------------------------------------
URL_COMPARADOR = BASE + "/landingPage/CompararTramites"


def _datos_comparador(t):
    return {
        "tiempo_estimado_dias": t.get("tiempoEstimadoDias"),
        "nivel_complejidad": t.get("nivelComplejidad"),
        "puntaje_complejidad": t.get("scoreComplejidad"),
        "siglas_institucion": t.get("siglaInstitucion"),
    }


def consultar_comparador(cliente, ids):
    """Devuelve ({id: datos}, {id: error}). Agrupa de 3 en 3, como lo permite el portal.
    Si un grupo falla, consulta cada trámite junto a otro que ya respondió bien."""
    ids = [int(x) for x in ids]
    datos, errores = {}, {}

    def consulta(grupo):
        r = cliente.enviar_json(URL_COMPARADOR, grupo)
        if not isinstance(r, dict) or not r.get("success"):
            return None, (r or {}).get("message") if isinstance(r, dict) else "respuesta no reconocida"
        return {int(t["id"]): _datos_comparador(t) for t in r.get("tramites", []) if "id" in t}, None

    grupos = [ids[i:i + 3] for i in range(0, len(ids), 3)]
    pendientes = []
    for g in grupos:
        if len(g) == 1:
            pendientes += g
            continue
        try:
            res, msg = consulta(g)
        except BloqueoDelSitio:
            raise
        except Exception as e:  # noqa: BLE001
            res, msg = None, f"{type(e).__name__}: {e}"
        if res is None:
            pendientes += g
        else:
            datos.update(res)
    for id_ in pendientes:
        if id_ in datos:
            continue
        # primero con trámites que ya respondieron bien; si no hay, con cualquier otro (hasta tres intentos)
        companeros = [k for k in datos if k != id_] + [k for k in ids if k != id_ and k not in datos]
        if not companeros:
            errores[id_] = "el comparador necesita al menos dos trámites"
            continue
        msg = None
        for companero in companeros[:3]:
            try:
                res, msg = consulta([id_, companero])
            except BloqueoDelSitio:
                raise
            except Exception as e:  # noqa: BLE001
                res, msg = None, f"{type(e).__name__}: {e}"
            if res and id_ in res:
                datos.update(res)
                break
        else:
            errores[id_] = msg or "sin respuesta del comparador"
    return datos, errores


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------
def url_listado(pagina=1, institucion=None):
    q = {"page": pagina}
    if institucion:
        q["institutionFilter"] = institucion
    return URL_LISTADO + "?" + urllib.parse.urlencode(q)


def parsear_listado(html: str) -> dict:
    raiz = analizar(html)
    sel = raiz.primero(tag="select", id="institutionFilter")
    instituciones = []
    if sel:
        for o in sel.buscar(tag="option"):
            v = (o.get("value") or "").strip()
            if v:
                instituciones.append((v, texto_unico(o.texto())))
    tramites = []
    for a in raiz.buscar(tag="article", clase="tramite-card"):
        tid = (a.get("data-tramite-id") or "").strip()
        if not tid.isdigit():
            enlace = a.primero(tag="a", clase="diger-rrow__cta")
            m = re.search(r"DetalleTramite/(\d+)", enlace.get("href", "") if enlace else "")
            tid = m.group(1) if m else ""
        if not tid:
            continue
        tit = a.primero(clase="diger-rrow__title")
        inst = a.primero(clase="diger-rrow__eyebrow")
        mod = a.primero(clase="diger-modbadge")
        tramites.append({
            "id": int(tid),
            "titulo": texto_unico(tit.texto()) if tit else "",
            "institucion": texto_unico(inst.texto()) if inst else "",
            "modalidad": texto_unico(mod.texto()) if mod else "",
        })
    paginas = [1]
    for enlace in raiz.buscar(tag="a"):
        m = re.search(r"[?&]page=(\d+)", enlace.get("href", ""))
        if m:
            paginas.append(int(m.group(1)))
    return {"instituciones": instituciones, "tramites": tramites, "paginas": max(paginas)}


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------
def _pares_meta(cuerpo):
    pares = []
    for m in cuerpo.buscar(clase="dt-list__meta"):
        et = m.primero(clase="dt-list__meta-label")
        va = m.primero(clase="dt-list__meta-value")
        etiqueta = texto_unico(et.texto()) if et else ""
        etiqueta = re.sub(r"\s*:\s*$", "", etiqueta)
        valor = lineas(va.texto()) if va else lineas(m.texto(excluir_clases=("dt-list__meta-label",)))
        pares.append({"etiqueta": etiqueta, "valor": valor})
    return pares


def _enlaces(nodo):
    salida = []
    for a in nodo.buscar(tag="a"):
        href = (a.get("href") or "").strip()
        if "__cf_email__" in a.clases:
            continue   # en el portal se ve como texto (el correo), no como enlace
        if "/cdn-cgi/l/email-protection#" in href:
            correo = correo_cloudflare(href.split("#", 1)[1])
            href = f"mailto:{correo}" if correo else href
        if href:
            salida.append({"texto": texto_unico(a.texto()), "url": href})
    return salida


def _panel(p):
    lista = p.primero(tag="ul", clase="dt-list")
    if lista:
        elementos = []
        for li in lista.buscar(tag="li", clase="dt-list__item", directos=True):
            marca = li.primero(clase="dt-list__mark")
            cuerpo = li.primero(clase="dt-list__body") or li
            tit = cuerpo.primero(clase="dt-list__title")
            documentos = []
            for prev in cuerpo.buscar(clase="documento-preview"):
                for n in prev.elementos():
                    u = n.get("src") or n.get("href") or n.get("data")
                    if n.tag in ("iframe", "a", "embed", "object") and u:
                        documentos.append(u.strip())
            otros = lineas(cuerpo.texto(excluir_clases=("dt-list__title", "dt-list__meta", "documento-preview")))
            elementos.append({
                "marca": texto_unico(marca.texto()) if marca else "",
                "texto": lineas(tit.texto()) if tit else [],
                "meta": _pares_meta(cuerpo),
                "documentos": documentos,
                "enlaces": _enlaces(tit) if tit else [],
                "otros": otros,
            })
        return {"tipo": "lista", "elementos": elementos}
    lugares = p.primero(clase="lugares-list")
    if lugares:
        tarjetas = []
        for c in lugares.buscar(clase="lugar-card"):
            t = c.primero(clase="lugar-title")
            datos = []
            for it in c.buscar(clase="lugar-info-item"):
                et = it.primero(clase="lugar-info-label")
                va = it.primero(clase="lugar-info-value")
                datos.append({"etiqueta": texto_unico(et.texto()) if et else "",
                              "valor": lineas(va.texto()) if va else []})
            tarjetas.append({"titulo": lineas(t.texto()) if t else [], "datos": datos, "enlaces": _enlaces(c)})
        return {"tipo": "lugares", "lugares": tarjetas}
    tabla = p.primero(tag="table")
    if tabla:
        encabezados = [texto_unico(th.texto()) for th in tabla.buscar(tag="th")]
        filas = []
        for tr in tabla.buscar(tag="tr"):
            celdas = tr.buscar(tag="td")
            if not celdas:
                continue
            filas.append({"celdas": [texto_unico(td.texto()) for td in celdas], "enlaces": _enlaces(tr)})
        return {"tipo": "tabla", "encabezados": encabezados, "filas": filas}
    return {"tipo": "texto", "lineas": lineas(p.texto()), "enlaces": _enlaces(p)}


def parsear_ficha(html: str, id_portal: int) -> dict:
    raiz = analizar(html)
    main = raiz.primero(tag="main") or raiz
    h1 = main.primero(tag="h1", clase="dt-title")
    if h1 is None:
        raise FichaInvalida(f"La página del trámite {id_portal} no tiene título de ficha")
    eyebrow = main.primero(clase="dt-eyebrow")
    desc = main.primero(tag="p", clase="dt-desc")
    metarow = main.primero(clase="dt-metarow")
    modalidad, numero, etiquetas = None, None, []
    if metarow:
        badge = metarow.primero(clase="diger-modbadge")
        modalidad = texto_unico(badge.texto()) if badge else None
        for chip in metarow.buscar(clase="dt-chip"):
            t = texto_unico(chip.texto())
            m = re.fullmatch(r"N\.?\s*[ºo°]\s*(\d+)", t)
            if m:
                numero = m.group(1)
            elif t:
                etiquetas.append(t)
    accion = None
    acciones = main.primero(clase="dt-actions")
    if acciones:
        a = acciones.primero(tag="a", clase="btn-iniciar")
        if a is not None:
            accion = {"texto": texto_unico(a.texto()), "url": (a.get("href") or "").strip()}
    datos = []
    for card in main.buscar(clase="info-card"):
        t = card.primero(clase="info-card-title")
        c = card.primero(clase="info-card-content")
        datos.append({"titulo": texto_unico(t.texto()) if t else "", "lineas": lineas(c.texto()) if c else []})

    paneles = {p.get("id"): p for p in main.buscar(clase="tab-pane") if p.get("id")}
    pestanas, usados = [], set()
    for b in main.buscar(tag="button", clase="tab-button"):
        m = re.search(r"showTab\(\s*['\"]([^'\"]+)['\"]\s*\)", b.get("onclick", ""))
        if not m:
            continue
        clave = m.group(1)
        p = paneles.get("tab-" + clave)
        if p is None:
            continue
        usados.add("tab-" + clave)
        pestanas.append({"clave": clave, "etiqueta": texto_unico(b.texto()), "contenido": _panel(p)})
    for pid, p in paneles.items():
        if pid not in usados:
            pestanas.append({"clave": pid.replace("tab-", "", 1), "etiqueta": pid.replace("tab-", "", 1), "contenido": _panel(p)})

    return {
        "id_portal": int(id_portal),
        "titulo": texto_unico(h1.texto()),
        "institucion": texto_unico(eyebrow.texto(excluir_clases=("diger-emark",))) if eyebrow else "",
        "descripcion": lineas(desc.texto()) if desc else [],
        "modalidad": modalidad,
        "numero": numero,
        "etiquetas": etiquetas,
        "accion": accion,
        "datos": datos,
        "pestanas": pestanas,
    }


# ---------------------------------------------------------------------------
# Campos con nombre propio: solo se toman de un dato rotulado en el portal
# ---------------------------------------------------------------------------
def _clave(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(":", " ").split())


PATRONES = {
    "responsable": r"^responsable$",
    "objetivo": r"^objetivo$",
    "dirigido_a": r"^dirigido a$",
    "costo": r"^(costo|costos|tasa|tasas|arancel|aranceles|precio|valor)\b",
    "tiempo_respuesta": r"^tiempo\b",
    "marco_legal": r"^(marco legal|base legal|fundamento legal|marco juridico|base juridica|normativa)\b",
    "actualizado_portal": r"actualiz",
}


def buscar_rotulo(ficha, campo):
    """Devuelve las líneas de un dato cuyo rótulo en el portal coincide con el campo, o None.
    Busca en los datos principales, en los rótulos de las pestañas y en los rótulos internos."""
    patron = re.compile(PATRONES[campo])
    for d in ficha["datos"]:
        if patron.search(_clave(d["titulo"])):
            return d["lineas"]
    for p in ficha["pestanas"]:
        if patron.search(_clave(p["etiqueta"])):
            return contenido_en_lineas(p["contenido"])
        c = p["contenido"]
        if c["tipo"] == "lista":
            for e in c["elementos"]:
                for par in e["meta"]:
                    if patron.search(_clave(par["etiqueta"])):
                        return par["valor"]
    return None


def contenido_en_lineas(c):
    if c["tipo"] == "lista":
        return [" ".join(e["texto"]) for e in c["elementos"]]
    if c["tipo"] == "lugares":
        return [" ".join(l["titulo"]) for l in c["lugares"]]
    if c["tipo"] == "tabla":
        return [" | ".join(f["celdas"]) for f in c["filas"]]
    return list(c.get("lineas", []))


def campos(ficha):
    """Valores para las propiedades. Si el portal no rotula el dato, queda 'No consta en el portal'."""
    def una(campo):
        v = buscar_rotulo(ficha, campo)
        return " ".join(v) if v else NO_CONSTA
    dirigido = buscar_rotulo(ficha, "dirigido_a")
    return {
        "responsable": una("responsable"),
        "objetivo": una("objetivo"),
        "dirigido_a": list(dirigido) if dirigido else [NO_CONSTA],
        "costo": una("costo"),
        "tiempo_respuesta": una("tiempo_respuesta"),
        "marco_legal": buscar_rotulo(ficha, "marco_legal"),
        "actualizado_portal": una("actualizado_portal"),
        "modalidad": ficha.get("modalidad") or NO_CONSTA,
        "url_inicio": (ficha.get("accion") or {}).get("url") or NO_CONSTA,
    }


def json_canonico(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
