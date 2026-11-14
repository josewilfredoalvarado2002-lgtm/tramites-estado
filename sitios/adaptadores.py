"""
Adaptadores: cada uno sabe leer un TIPO de sitio, no una institución.

- descargas_wpdm: sitios WordPress con "Download Manager" (fichas con PDF de requisitos). Ej.: SAR.
- paginas: lista de páginas escogidas; se copia el contenido por secciones (encabezados). Ej.: ONCAE, CNBS.
"""
import hashlib
import re
from urllib.parse import unquote, urljoin, urlparse

from estructura import analizar_documento
from nucleo import DominioNoVerificado, Ficha, limpiar, log, texto_documento

RUIDO = ["script", "style", "nav", "header", "footer", "form", "aside", "noscript", "iframe", "svg"]
_RUIDO_RE = re.compile(r"(^|[-_])(sidebar|widget|share|sharing|social|breadcrumbs?|menu|cookie|comments?|related|"
                       r"similar|navigation|pagination|buzon)([-_]|$)", re.I)


def RUIDO_CLASES(clase):
    """Clase de ruido (menús, barras laterales...). Las clases de los constructores de páginas
    (elementor-*, et_pb_*) envuelven el contenido y nunca cuentan como ruido."""
    if not clase or clase.startswith(("elementor-", "et_pb_", "e-con", "wp-block")) and "menu" not in clase:
        return False
    return bool(_RUIDO_RE.search(clase)) or clase == "wpdm-download-link"


def _texto_bloque(nodo):
    for br in nodo.find_all("br"):
        br.replace_with("\n")
    for li in nodo.find_all("li"):
        li.insert(0, "• ")
        li.append("\n")
    for p in nodo.find_all(["p", "div", "tr", "h5", "h6"]):
        p.append("\n")
    lineas = [limpiar(l) for l in nodo.get_text().splitlines()]
    return "\n".join(l for l in lineas if l and l != "•")


def secciones_por_encabezados(contenedor):
    """Parte el contenido en secciones usando h1-h4 (y strong que ocupa una línea sola)."""
    secciones, actual, buffer = {}, "Contenido", []

    def cerrar():
        t = "\n".join(buffer).strip()
        if t:
            k = actual
            n = 2
            while k in secciones:
                k = f"{actual} ({n})"
                n += 1
            secciones[k] = t

    for el in contenedor.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "div"], recursive=True):
        if el.find_parent(["ul", "ol", "table", "p"]) is not None:
            continue
        if el.name == "div" and el.find(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "div"]):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            cerrar()
            buffer = []
            actual = limpiar(el.get_text(" "))[:120] or "Contenido"
            continue
        t = _texto_bloque(el)
        if t:
            buffer.append(t)
    cerrar()
    return secciones


def _contenedor_principal(sopa):
    for x in sopa(RUIDO):
        x.decompose()
    total = len(sopa.get_text(strip=True)) or 1
    for x in sopa.find_all(class_=RUIDO_CLASES):
        if x.decomposed or x.attrs is None or x.name in ("body", "html", "main", "article"):
            continue
        # una clase "menu"/"share" en un contenedor grande no es ruido: es el envoltorio del tema
        if len(x.get_text(strip=True)) > 0.3 * total:
            continue
        x.decompose()
    for sel in ["#main-content", ".entry-content", "article", "main", "#content", ".site-main"]:
        c = sopa.select_one(sel)
        if c and len(c.get_text(strip=True)) > 200:
            return c
    return sopa.body or sopa


def _id_wordpress(sopa, url):
    cuerpo = " ".join(sopa.body.get("class", [])) if sopa.body else ""
    m = re.search(r"(?:page-id|postid)-(\d+)", cuerpo)
    if m:
        return m.group(1)
    enlace = sopa.find("link", rel="shortlink")
    if enlace and "p=" in enlace.get("href", ""):
        return enlace["href"].split("p=")[-1]
    return hashlib.sha1(url.encode()).hexdigest()[:8]


def _documentos(cli, contenedor, url_pagina, maximo=6):
    docs, vistos = [], set()
    for a in contenedor.find_all("a", href=True):
        u = urljoin(url_pagina, a["href"])
        if not _es_documento(u) or u in vistos or re.search(r"\.(jpe?g|png)$", u, re.I) and not re.search(
                r"requisit|descargar|recurso", a.get_text(" ") + u, re.I):
            continue
        vistos.add(u)
        nombre = limpiar(a.get_text(" ")) or u.rsplit("/", 1)[-1]
        if not cli.permitido(u):
            docs.append({"nombre": nombre, "url": u, "texto": "", "aviso": "enlace a un dominio no verificado: no se leyó"})
            continue
        if len(docs) >= maximo:
            docs.append({"nombre": nombre, "url": u, "texto": "", "aviso": "no se leyó (límite por página)"})
            continue
        try:
            t, aviso = texto_documento(cli, u)
        except Exception as e:
            t, aviso = "", f"no se pudo descargar ({e})"
        docs.append({"nombre": nombre, "url": u, "texto": t, "aviso": aviso})
    return docs


# --------------------------------------------------------------- páginas escogidas
def paginas(cli, siglas, urls, dividir=False, omitir=None):
    fichas, errores = [], []
    for item in urls:
        url, tipo = (item, "tramite") if isinstance(item, str) else (item["url"], item.get("tipo", "tramite"))
        try:
            sopa, final = cli.sopa(url)
        except Exception as e:
            errores.append(f"{url}: {e}")
            log(f"  ERROR {url}: {e}")
            continue
        titulo = ""
        og = sopa.find("meta", property="og:title")
        h1 = sopa.find("h1")
        if h1 and limpiar(h1.get_text(" ")):
            titulo = limpiar(h1.get_text(" "))
        elif og:
            titulo = og.get("content", "")
        else:
            titulo = limpiar(sopa.title.get_text()) if sopa.title else url
        titulo = re.sub(rf"\s*[-–|]\s*({re.escape(siglas)}\b|(Secretar|Comisi|Direcci|Instituto|Administraci|Procuradur|Oficina|Servicio)\w*\s+(de|Nacional|General)).*$",
                        "", titulo).strip() or titulo
        mod = sopa.find("meta", property="article:modified_time")
        id_local = _id_wordpress(sopa, final)
        cont = _contenedor_principal(sopa)
        docs = _documentos(cli, cont, final)
        f = Ficha(siglas=siglas, id_local=id_local, titulo=titulo, url_ficha=final, tipo=tipo,
                  actualizado_fuente=(mod.get("content", "")[:10] if mod else ""),
                  secciones=secciones_por_encabezados(cont), documentos=docs)
        for d in docs:
            if d["texto"]:
                volcar(f, d)
            if d.get("aviso"):
                f.avisos.append(f"{d['nombre']}: {d['aviso']}")
        if dividir:
            # cada sección de la página es un trámite distinto (p. ej. TSC "Servicios prestados")
            vistos_t = set()
            titulos_sec = {re.sub(r"\s*\(\d+\)$", "", k) for k in f.secciones}
            for k, v in f.secciones.items():
                # el texto de una sección termina donde aparece el título de otra (páginas con pestañas repetidas)
                lineas = v.split("\n")
                corte = next((i for i, l in enumerate(lineas) if i > 0 and l.strip() in titulos_sec), len(lineas))
                v = "\n".join(lineas[:corte])
                tk = re.sub(r"\s*\(\d+\)$", "", k)
                if tk in ("Contenido", titulo) or tk in vistos_t or len(v) < 150 or (omitir and re.search(omitir, tk, re.I)):
                    continue
                vistos_t.add(tk)
                fichas.append(Ficha(siglas=siglas, id_local=hashlib.sha1(tk.lower().encode()).hexdigest()[:8], titulo=tk,
                                    url_ficha=final, tipo=tipo, categoria=titulo,
                                    actualizado_fuente=f.actualizado_fuente, secciones={"Contenido": v}))
                log(f"  {siglas} sección: {tk[:60]}")
            continue
        fichas.append(f)
        log(f"  {siglas} página: {titulo[:60]} ({len(f.secciones)} secciones, {len(docs)} documentos)")
    return fichas, errores


# --------------------------------------------------------------- WordPress Download Manager
def _items_categoria(cli, base_url, slug):
    items, pagina = [], 1
    while pagina <= 30:
        url = f"{base_url}/download-category/{slug}/" + (f"page/{pagina}/" if pagina > 1 else "")
        try:
            sopa, _ = cli.sopa(url)
        except RuntimeError:
            break  # no hay más páginas
        nuevos = 0
        for art in sopa.select("article.wpdmpro, article.type-wpdmpro"):
            a = art.select_one(".entry-title a, h2 a, h3 a, h4 a")
            m = re.search(r"post-(\d+)", " ".join(art.get("class", [])))
            if not a or not m:
                continue
            fecha = art.select_one(".date_label, .post-date")
            items.append({"id": m.group(1), "titulo": limpiar(a.get_text(" ")), "url": a["href"],
                          "fecha_listado": limpiar(fecha.get_text()) if fecha else ""})
            nuevos += 1
        if not nuevos or not sopa.find("a", href=re.compile(rf"/download-category/{slug}/page/{pagina + 1}/")):
            break
        pagina += 1
    return items


def _detalle_wpdm(sopa):
    """Lee 'Última actualización', 'Descripción' y el enlace de descarga de la ficha."""
    texto = sopa.get_text("\n")
    act = re.search(r"Última actualización\s*\n+\s*([^\n]+)", texto)
    desc = ""
    h = sopa.find(lambda t: t.name in ("h2", "h3", "h4", "div", "strong") and limpiar(t.get_text()) == "Descripción")
    if h:
        bloque = h.find_next(["div", "p"])
        if bloque:
            d = limpiar(bloque.get_text(" "))
            if d and "Categorías" not in d[:20] and "[free_download_btn]" not in d:
                desc = d
    descarga = next((a["href"] for a in sopa.find_all("a", href=True) if "wpdmdl=" in a["href"]), "")
    return (limpiar(act.group(1)) if act else ""), desc, descarga


def descargas_wpdm(cli, siglas, base_url, categorias, limite=None):
    """categorias: {slug: (tipo, etiqueta)}. Las fichas que están en varias categorías se leen una vez."""
    por_id, errores = {}, []
    for slug, (tipo, etiqueta) in categorias.items():
        items = _items_categoria(cli, base_url, slug)
        log(f"  {siglas} categoría {slug}: {len(items)} fichas")
        for it in items:
            if it["id"] in por_id:
                if etiqueta not in por_id[it["id"]]["categorias"]:
                    por_id[it["id"]]["categorias"].append(etiqueta)
                continue
            por_id[it["id"]] = dict(it, tipo=tipo, categorias=[etiqueta])
    lista = list(por_id.values())[:limite] if limite else list(por_id.values())
    fichas = []
    for n, it in enumerate(lista, 1):
        try:
            sopa, final = cli.sopa(it["url"])
            actualizado, desc, descarga = _detalle_wpdm(sopa)
            f = Ficha(siglas=siglas, id_local=it["id"], titulo=it["titulo"], url_ficha=final, tipo=it["tipo"],
                      categoria=", ".join(it["categorias"]), actualizado_fuente=actualizado or it["fecha_listado"])
            if desc:
                f.secciones["Descripción"] = desc
            if descarga:
                try:
                    t, aviso = texto_documento(cli, descarga)
                except DominioNoVerificado as e:
                    t, aviso = "", str(e)
                nombre_doc = it["titulo"]
                d = {"nombre": nombre_doc, "url": descarga.split("&refresh=")[0], "texto": t, "aviso": aviso}
                f.documentos.append(d)
                if t:
                    volcar(f, d)
                if aviso:
                    f.avisos.append(aviso)
            else:
                f.avisos.append("la ficha no tiene enlace de descarga")
            fichas.append(f)
        except Exception as e:
            errores.append(f"{it['url']}: {e}")
            log(f"  ERROR {it['url']}: {e}")
        if n % 20 == 0:
            log(f"  {siglas}: {n}/{len(lista)} fichas leídas")
    return fichas, errores


# --------------------------------------------------------------- utilidades comunes de documentos
_VACIO = re.compile(r"^(ver|descargar|download|aqu[ií]|clic aqu[ií]|n/?a|-|—|pdf|picture_as_pdf descargar pdf)$", re.I)


def _leer_doc(cli, nombre, url, leer=True):
    url = url.strip()
    if not cli.permitido(url):
        return {"nombre": nombre, "url": url, "texto": "", "aviso": "enlace a un dominio no verificado: no se leyó"}
    if not leer:
        return {"nombre": nombre, "url": url, "texto": "", "aviso": ""}
    try:
        t, aviso = texto_documento(cli, url)
    except Exception as e:
        t, aviso = "", f"no se pudo descargar ({e})"
        if ".." in url.rsplit("/", 1)[-1]:
            # enlace roto en el propio sitio (p. ej. "archivo..pdf"): se prueba el mismo archivo con un solo punto
            alterna = re.sub(r"\.\.(pdf|docx?)", r".\1", url, flags=re.I)
            try:
                t, aviso2 = texto_documento(cli, alterna)
                aviso = (f"el enlace del sitio está roto ({url.rsplit('/', 1)[-1]}); se leyó el mismo archivo "
                         f"en {alterna}" + (f" — {aviso2}" if aviso2 else ""))
                url = alterna
            except Exception:
                pass
    return {"nombre": nombre, "url": url, "texto": t, "aviso": aviso}


def _es_documento(url):
    return bool(re.search(r"\.(pdf|docx?|xlsx?|jpe?g|png)(\?|$)|download|descargar|/assets/|wpdmdl=", url.strip(), re.I))


def _id_texto(t):
    return hashlib.sha1(norm_id(t).encode()).hexdigest()[:8]


def norm_id(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def volcar(f, d):
    """Ordena el texto de un documento por partes (para qué, requisitos, costo...) y lo agrega a la ficha.
    Marca el documento como formulario si es solo campos para llenar."""
    a = analizar_documento(d["texto"], f.titulo, d.get("nombre", ""))
    d["formulario"] = a["formulario"] and not a["requisitos"]
    for k, v in a["secciones"].items():
        clave = k if k not in f.secciones else f"{k} — {d['nombre']}"
        n = 2
        while clave in f.secciones:
            clave, n = f"{k} — {d['nombre']} ({n})", n + 1
        f.secciones[clave] = v


def _agregar_docs(f, docs):
    for d in docs:
        f.documentos.append(d)
        if d["texto"]:
            volcar(f, d)
        if d.get("aviso"):
            f.avisos.append(f"{d['nombre']}: {d['aviso']}")


# --------------------------------------------------------------- tablas (una fila = un trámite)
def tabla(cli, siglas, urls, col_titulo, col_id=None, col_categoria=None, tipo="tramite"):
    """Cada fila de las tablas de la página es un trámite. Las celdas con texto se copian como secciones
    (con el nombre de su columna); las celdas con enlaces a documentos se descargan y se copian."""
    fichas, errores, vistos = [], [], set()
    for url in urls:
        try:
            sopa, final = cli.sopa(url)
        except Exception as e:
            errores.append(f"{url}: {e}")
            continue
        cont = _contenedor_principal(sopa)
        for t in cont.find_all("table"):
            filas = t.find_all("tr")
            if not filas:
                continue
            cab = [limpiar(c.get_text(" ")) for c in filas[0].find_all(["th", "td"])]
            if col_titulo not in cab:
                continue
            h = t.find_previous(["h1", "h2", "h3", "h4"])
            categoria_tabla = limpiar(h.get_text(" ")) if h else ""
            for fila in filas[1:]:
                celdas = fila.find_all(["td", "th"])
                if len(celdas) != len(cab):
                    continue
                valores = dict(zip(cab, celdas))
                titulo = limpiar(valores[col_titulo].get_text(" "))
                if not titulo or titulo == col_titulo:
                    continue
                idl = limpiar(valores[col_id].get_text()) if col_id and col_id in valores else _id_texto(titulo)
                if idl in vistos:
                    continue
                vistos.add(idl)
                cat = limpiar(valores[col_categoria].get_text(" ")) if col_categoria in valores else categoria_tabla
                f = Ficha(siglas=siglas, id_local=idl, titulo=titulo, url_ficha=final, tipo=tipo, categoria=cat)
                docs = []
                for col, celda in valores.items():
                    if col in (col_titulo, col_id, col_categoria):
                        continue
                    enlaces = [a for a in celda.find_all("a", href=True) if _es_documento(a["href"])]
                    escondido = [unquote(a["href"]).strip() for a in celda.find_all("a", href=True)
                                 if not _es_documento(a["href"]) and " " in a["href"].strip()]
                    texto = _texto_bloque(celda)
                    if escondido and (not texto or _VACIO.match(texto)):
                        # el sitio guardó el texto dentro del enlace en vez de mostrarlo
                        texto = "\n".join(escondido)
                        f.avisos.append(f"{col.capitalize()}: el sitio tiene este texto dentro del enlace «Ver»; se copió de ahí")
                    if texto and not _VACIO.match(texto):
                        f.secciones[col.capitalize()] = texto
                    for a in enlaces:
                        nombre = limpiar(a.get_text(" "))
                        nombre = f"{col.capitalize()} — {titulo}" if not nombre or _VACIO.match(nombre) else nombre
                        d = _leer_doc(cli, nombre, urljoin(final, a["href"]))
                        d["seccion"] = f"{col.capitalize()} (texto del documento oficial)"
                        docs.append(d)
                _agregar_docs(f, docs)
                fichas.append(f)
                log(f"  {siglas} fila: {titulo[:60]} ({len(f.secciones)} secciones, {len(docs)} documentos)")
    return fichas, errores


# --------------------------------------------------------------- bloques (un bloque = un trámite)
def bloques(cli, siglas, urls, bloque, titulo, leer=None, tipo="tramite", categoria=""):
    """bloque/titulo: selectores CSS. leer: expresión regular sobre el texto o la URL del enlace que
    indica qué documentos se descargan y copian (los demás solo se enlazan). Sin 'leer' se leen todos."""
    fichas, errores, vistos = [], [], set()
    for url in urls:
        try:
            sopa, final = cli.sopa(url)
        except Exception as e:
            errores.append(f"{url}: {e}")
            continue
        h1 = sopa.find("h1")
        cat = categoria or (limpiar(h1.get_text(" ")) if h1 else "")
        if not sopa.select(bloque):
            t = limpiar(sopa.title.get_text()) if sopa.title else ""
            errores.append(f"{url}: la página no trae bloques «{bloque}» (título recibido: «{t[:80]}», "
                           f"{len(sopa.get_text())} caracteres): puede ser un bloqueo del sitio")
            log(f"  ERROR {errores[-1]}")
        for b in sopa.select(bloque):
            tn = b.select_one(titulo)
            tit = limpiar(tn.get_text(" ")) if tn else ""
            if not tit:
                continue
            idl = _id_texto(tit)
            if idl in vistos:
                continue
            vistos.add(idl)
            enlace_titulo = tn.find("a", href=True) if tn.name != "a" else tn
            url_ficha = urljoin(final, enlace_titulo["href"]) if enlace_titulo else final
            f = Ficha(siglas=siglas, id_local=idl, titulo=tit, url_ficha=url_ficha, tipo=tipo, categoria=cat)
            for x in b.select(titulo):
                x.extract()
            docs, urls_vistas = [], set()
            for a in b.find_all("a", href=True):
                u = urljoin(final, a["href"]).strip()
                if u in urls_vistas or not _es_documento(u):
                    continue
                urls_vistas.add(u)
                nombre = " ".join(a.get_text(" ").split()).replace("download ", "").replace("picture_as_pdf ", "")
                nombre = tit if not nombre or _VACIO.match(nombre) else nombre
                quiere = not leer or re.search(leer, nombre + " " + u, re.I)
                d = _leer_doc(cli, nombre, u, leer=bool(quiere))
                if quiere:
                    d["seccion"] = "Requisitos (texto del documento oficial)" if re.search(r"requisit", d["texto"][:400] + nombre, re.I) else None
                docs.append(d)
            for x in b.find_all(["a", "button"]):
                x.decompose()
            texto = _texto_bloque(b)
            texto = "\n".join(l for l in texto.split("\n") if len(l) > 25)
            if len(texto) > 80:
                f.secciones["Contenido"] = texto
            _agregar_docs(f, docs)
            fichas.append(f)
            log(f"  {siglas} bloque: {tit[:60]} ({len(f.secciones)} secciones, {len(docs)} documentos)")
    return fichas, errores


# --------------------------------------------------------------- documentos enlazados (un documento = un trámite)
def documentos_enlazados(cli, siglas, urls, filtro=None, tipo="tramite"):
    """Cada PDF/Word enlazado en la página es un trámite: título = texto del enlace, categoría = el
    encabezado bajo el que aparece. 'filtro' (regex) limita qué enlaces cuentan."""
    fichas, errores, vistos = [], [], set()
    for url in urls:
        try:
            sopa, final = cli.sopa(url)
        except Exception as e:
            errores.append(f"{url}: {e}")
            continue
        cont = _contenedor_principal(sopa)
        for a in cont.find_all("a", href=True):
            u = urljoin(final, a["href"]).strip()
            if not _es_documento(u):
                continue
            clave = re.sub(r"[?#].*$", "", u)
            nombre = limpiar(a.get_text(" "))
            nombre = re.sub(r"\(\s*\d[\d.,]*\s*descargas?\s*\)", "", nombre, flags=re.I).strip()
            nombre = re.sub(r"\.(pdf|docx?|xlsx?)$", "", nombre, flags=re.I).strip()
            if not nombre or _VACIO.match(nombre):
                nombre = unquote(clave.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
            if clave in vistos or (filtro and not re.search(filtro, nombre + " " + u, re.I)):
                continue
            vistos.add(clave)
            h = a.find_previous(["h1", "h2", "h3", "h4", "h5"])
            cat = limpiar(h.get_text(" "))[:100] if h else ""
            if re.match(r"^ver\b", nombre, re.I) and cat:
                # "Ver formulario" no dice nada: se usa el encabezado del trámite bajo el que está
                nombre = f"{cat} — {nombre[4:].strip() or 'documento'}"
            f = Ficha(siglas=siglas, id_local=hashlib.sha1(clave.encode()).hexdigest()[:8], titulo=nombre,
                      url_ficha=final, tipo=tipo, categoria=cat)
            d = _leer_doc(cli, nombre, u)
            if d["texto"]:
                d["seccion"] = ("Requisitos (texto del documento oficial)" if re.search(r"requisit", d["texto"], re.I)
                                else "Texto del documento oficial")
            _agregar_docs(f, [d])
            fichas.append(f)
            log(f"  {siglas} documento: {nombre[:60]} ({'con texto' if d['texto'] else d['aviso'][:40]})")
    return fichas, errores


def _requisitos_acordeon(html):
    """Texto de un bloque de requisitos en acordeón: «1. Solicitud» seguido de su contenido."""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    for x in s.select(".accordion-icon, script, style"):
        x.decompose()
    items = s.select(".accordion-item-calculator")
    if not items:
        return _texto_bloque(s)
    partes = []
    for it in items:
        cab = it.select_one(".accordion-header")
        cue = it.select_one(".accordion-content")
        t = limpiar(cab.get_text(" ")) if cab else ""
        c = _texto_bloque(cue) if cue else ""
        if c and c.replace("\n", " ").strip() != t:
            # el contenido va sangrado bajo su número para que se lea como una sola entrada
            c = "\n".join("   " + l for l in c.split("\n"))
            partes.append(f"{t}\n{c}" if t else c)
        elif t:
            partes.append(t)
    return "\n".join(partes)


def calculadora(cli, siglas, urls, prefijo=r"requisitos?\s*:?\s*"):
    """Páginas con «Cost Calculator Builder» (WordPress): los requisitos de cada trámite vienen como
    bloques HTML dentro del JSON de la calculadora (atributo :content de <calc-builder-front>) y el
    sitio los muestra según lo que se elija en los menús. Cada bloque «Requisitos: X» es un trámite. Ej.: ARSA."""
    import json as _json
    fichas, errores, vistos = [], [], set()
    for url in urls:
        try:
            sopa, final = cli.sopa(url)
        except Exception as e:
            errores.append(f"{url}: {e}")
            log(f"  ERROR {url}: {e}")
            continue
        h1 = sopa.find("h1")
        cat = limpiar(h1.get_text(" ")) if h1 else ""
        if not cat and sopa.title:
            cat = re.sub(r"\s*[-–|].*$", "", limpiar(sopa.title.get_text()))
        calcs = sopa.find_all("calc-builder-front")
        if not calcs:
            errores.append(f"{url}: la página no trae la calculadora de trámites")
            log(f"  ERROR {errores[-1]}")
        slug = urlparse(final).path.strip("/").replace("/", "-") or "inicio"
        for c in calcs:
            try:
                datos = _json.loads(c.get(":content") or "{}")
            except ValueError as e:
                errores.append(f"{url}: JSON de la calculadora ilegible ({e})")
                continue
            for campo in datos.get("fields", []):
                etiqueta = limpiar(campo.get("label") or "")
                html = campo.get("htmlContent") or ""
                if campo.get("_tag") != "cost-html" or not re.match(prefijo, etiqueta, re.I) or not html.strip():
                    continue
                titulo = re.sub(r"^" + prefijo, "", etiqueta, flags=re.I).strip(" :-") or etiqueta
                texto = _requisitos_acordeon(html)
                # id corto y estable: iniciales de la página + número del bloque («ab-6» = alimentos y bebidas, bloque 6)
                ini = "".join(w[0] for w in slug.split("-") if w and w not in ("y", "de", "del", "la", "las", "los"))
                num = re.search(r"(\d+)$", campo.get("alias") or "")
                idl = f"{ini}-{num.group(1)}" if num else f"{ini}-{_id_texto(titulo)}"
                if idl in vistos or len(texto) < 40:
                    continue
                vistos.add(idl)
                f = Ficha(siglas=siglas, id_local=idl, titulo=titulo, url_ficha=final, categoria=cat,
                          secciones={"Requisitos": texto})
                from bs4 import BeautifulSoup
                docs = []
                for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                    u = urljoin(final, a["href"]).strip()
                    if _es_documento(u) and urlparse(u).netloc == urlparse(final).netloc:
                        nombre = limpiar(a.get_text(" ")) or unquote(u.rsplit("/", 1)[-1])
                        docs.append(_leer_doc(cli, nombre, u, leer=False))
                _agregar_docs(f, docs)
                fichas.append(f)
        log(f"  {siglas} {cat or url}: {sum(1 for f in fichas if f.url_ficha == final)} trámites")
    return fichas, errores
