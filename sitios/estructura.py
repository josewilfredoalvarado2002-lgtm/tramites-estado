"""
Lee el texto de un documento oficial (PDF o Word) o de una página y lo ordena por partes:
para qué se hace, requisitos, costo, plazo, dónde se presenta, base legal, procedimiento y notas.

No resume ni redacta nada: cada parte es texto literal del documento, solo movido bajo su
encabezado. Lo que no se reconoce queda en "Otro texto del documento".

También decide si un documento es solo un formulario para llenar (campos en blanco, firma, sello)
y si trae requisitos. Un formulario sin requisitos, o un documento que no es un trámite, no se
guarda como trámite.
"""
import re
import unicodedata

PARTES = [  # (clave, título de la sección en la nota, patrón del encabezado)
    ("para_que", "Para qué se hace (según el documento)",
     r"descripci[oó]n|objet(o|ivo)s?\b|finalidad|prop[oó]sito|¿?\s*qu[eé] es\b|en qu[eé] consiste|definici[oó]n|"
     r"alcance|dirigido a|beneficiari|¿?\s*qui[eé]n(es)? (puede|debe|lo)|aplica para|generalidades|introducci[oó]n"),
    ("requisitos", "Requisitos (según el documento oficial)",
     r"requisit|informaci[oó]n (requerida|necesaria|a presentar)|documentos? (a presentar|requerid|necesari|que (se )?deb)|documentaci[oó]n (requerida|a presentar|necesaria)|"
     r"debe(r[aá])? (presentar|adjuntar|acompañar)"),
    ("costo", "Costo (según el documento)", r"costos?\b|tasas?\b|arancel|valor\b|monto|precio|pagos?\b|derechos? a pagar"),
    ("plazo", "Plazo (según el documento)", r"plazos?\b|tiempo (de|estimado|aproximado)|duraci[oó]n|vigencia|tiempo de respuesta"),
    ("donde", "Dónde se presenta (según el documento)",
     r"d[oó]nde\b|lugar (de|para)|ventanilla|horarios?\b|oficinas?\b|presentaci[oó]n de la solicitud|contacto"),
    ("base_legal", "Base legal (según el documento)", r"base legal|fundamentos? (legal|jur[ií]dico)|marco (legal|jur[ií]dico)|base jur[ií]dica"),
    ("procedimiento", "Procedimiento (según el documento)", r"procedimiento|pasos\b|proceso\b|flujo|etapas"),
    ("notas", "Notas (según el documento)", r"notas?\b|observaci[oó]n|observaciones|importante|aclaraci"),
]
TITULOS = {k: t for k, t, _ in PARTES}
ORDEN = [k for k, _, _ in PARTES] + ["otro"]
TITULOS["otro"] = "Otro texto del documento"

# frases que dicen para qué sirve el trámite aunque no haya un encabezado
_FRASES_PARA = re.compile(
    r"(tiene (por|como) (objeto|objetivo|finalidad)|con el (fin|objeto|prop[oó]sito) de|sirve para|permite (a|que|obtener|realizar)|"
    r"consiste en|est[aá] dirigid[oa]|se otorga|se emite|es el (documento|tr[aá]mite|proceso)|es un (documento|tr[aá]mite|proceso)|"
    r"tiene como prop[oó]sito|se utiliza para|mediante el cual|por medio del cual|a trav[eé]s del cual)", re.I)

_RUIDO_LINEA = re.compile(
    r"^(p[aá]gina\s*\d+(\s*(de|/)\s*\d+)?|\d+\s*(de|/)\s*\d+|v\.?\s*\d+(\.\d+)*|versi[oó]n\s*[\d.]+|"
    r"(https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+|tel[eé]fonos?:?[\d\s()+-]*|pbx:?[\d\s()+-]*)$", re.I)
_CASILLAS = re.compile(r"[☐□❒■▪◻◼✓✔�]")
_CAMPO = re.compile(r"_{4,}|\.{8,}|^\s*(firma|sello|huella|nombre( completo)?|fecha|lugar y fecha|no\.? de identidad|dni|rtn|"
                    r"direcci[oó]n|tel[eé]fono|correo( electr[oó]nico)?|cargo|para uso (exclusivo|interno))\s*[:_.]*\s*$", re.I)
_ITEM = re.compile(r"^\s*(\d{1,2}[.)-]|[a-z][.)]\s|[-•·*]\s|[ivx]{1,4}[.)])", re.I)


_DOC_PALABRAS = re.compile(r"\b(copia|original|fotocopia|escrito|solicitud|poder|dni|identidad|rtn|constancia|certificad|"
                           r"recibo|pago|carta|solvencia|escritura|permiso|licencia|documento|formulario|forma\b|"
                           r"declaraci[oó]n|presentar|adjuntar|acreditar|plano|estudio|contrato|pasaporte|fotograf)", re.I)
# letras que algunos PDF entregan mal codificadas (fuentes sin tabla de caracteres): nunca aparecen en español
_MAL_CODIFICADAS = str.maketrans({"Ø": "é", "Æ": "á", "œ": "ú", "æ": "ñ"})


def _lista_requisitos(texto):
    """Busca la tanda más larga de ítems enumerados que parecen documentos a presentar.
    Devuelve (antes, lista, despues) o None."""
    lineas = texto.splitlines()
    num = re.compile(r"^\s*\d{1,2}([.)-]|\s+(?=[A-ZÁÉÍÓÚÑ\d])|\s*$)")
    mejor, i = None, 0
    while i < len(lineas):
        if num.match(lineas[i]):
            j, items, docs = i, 0, 0
            while j < len(lineas) and not (lineas[j].strip() == "" and j + 1 < len(lineas) and
                                           not num.match(lineas[j + 1])):
                if num.match(lineas[j]):
                    items += 1
                    docs += bool(_DOC_PALABRAS.search(" ".join(lineas[j:j + 2])))
                j += 1
            if items >= 3 and docs / items >= 0.4 and (not mejor or items > mejor[2]):
                mejor = (i, j, items)
            i = j + 1
        else:
            i += 1
    if not mejor:
        return None
    a, b, _ = mejor
    return "\n".join(lineas[:a]).strip(), "\n".join(lineas[a:b]).strip(), "\n".join(lineas[b:]).strip()


def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


def _es_encabezado(linea):
    """¿La línea es un encabezado de parte? Devuelve la clave o None."""
    l = linea.strip().strip("*#").strip()
    if not l or len(l) > 95 or _ITEM.match(l) and not re.match(r"^\s*[ivx]{1,4}[.)]|^\s*\d{1,2}[.)]\s*[A-ZÁÉÍÓÚÑ ]{4,}$", l):
        return None
    letras = [c for c in l if c.isalpha()]
    mayus = letras and sum(c.isupper() for c in letras) / len(letras) > 0.7
    if not (mayus or l.endswith(":") or len(l) <= 40 and not l.endswith(".")):
        return None
    cabeza = re.sub(r"^[\W\d]+", "", l)[:45]
    for clave, _, patron in PARTES:
        if re.match(rf"^(¿\s*)?({patron})", cabeza, re.I):
            return clave
    return None


def limpiar_documento(texto):
    """Quita casillas, números de página, versiones sueltas y líneas repetidas en cada página
    (membretes y pies). Las páginas vienen separadas por \\f."""
    paginas = texto.split("\f")
    repetidas = set()
    if len(paginas) > 1:
        from collections import Counter
        cuenta = Counter(l.strip() for p in paginas for l in set(p.splitlines()) if l.strip())
        # membretes y pies que se repiten en cada página (los encabezados de parte se conservan)
        repetidas = {l for l, n in cuenta.items() if n >= max(2, len(paginas) * 0.6) and len(l) < 120
                     and not _es_encabezado(l)}
    salida = []
    for l in texto.replace("\f", "\n").splitlines():
        l = _CASILLAS.sub("", l).strip()
        if not l or l in repetidas or _RUIDO_LINEA.match(l):
            if salida and salida[-1] != "":
                salida.append("")
            continue
        salida.append(l)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(salida)).strip()


def _frases_para(texto, maximo=3):
    frases = re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿])", re.sub(r"\s*\n\s*", " ", texto))
    elegidas = [f.strip() for f in frases if _FRASES_PARA.search(f) and 30 <= len(f) <= 600]
    return elegidas[:maximo]


def partes(texto):
    """Divide el texto en partes reconocidas. Devuelve {clave: texto} en el orden del documento."""
    res, actual, buf = {}, "otro", []

    def cerrar():
        t = "\n".join(buf).strip()
        if t:
            res[actual] = (res[actual] + "\n\n" + t) if actual in res else t

    for linea in texto.splitlines():
        clave = _es_encabezado(linea)
        if clave:
            cerrar()
            buf, actual = [], clave
            resto = linea.strip()
            # el encabezado se conserva como primera línea si dice algo más que la palabra clave
            if len(resto) > 25 or not resto.endswith(":"):
                buf.append(resto)
            continue
        buf.append(linea)
    cerrar()
    return res


def es_formulario(texto):
    lineas = [l for l in texto.splitlines() if l.strip()]
    if not lineas:
        return False
    campos = sum(1 for l in lineas if _CAMPO.search(l))
    return campos >= 6 or campos / len(lineas) > 0.2


def cuenta_requisitos(texto):
    """Cuántas líneas de requisitos hay (ítems enumerados, o líneas con contenido)."""
    lineas = [l for l in (texto or "").splitlines() if l.strip()]
    items = sum(1 for l in lineas if _ITEM.match(l))
    return items or max(0, len(lineas) - 1)


def analizar_documento(texto, titulo="", nombre=""):
    """Para un documento leído: {secciones: {título: texto}, para_que, requisitos (n), formulario (bool)}."""
    if sum(texto.count(c) for c in "ØÆœæ") >= 3:
        texto = texto.translate(_MAL_CODIFICADAS)
    limpio = limpiar_documento(texto)
    p = partes(limpio)
    para = p.get("para_que", "")
    if not para:
        frases = _frases_para(p.get("otro", "") or limpio)
        if frases:
            para = "\n".join(frases)
            p = {"para_que": para, **p}
    if "requisitos" not in p and "otro" in p and re.search(r"requisit", limpio[:500], re.I) \
            and cuenta_requisitos(p["otro"]) >= 2:
        # documento titulado «Requisitos…» sin encabezado propio: todo el cuerpo es la lista de requisitos
        p["requisitos"] = p.pop("otro")
    if "requisitos" not in p:
        corte = _lista_requisitos(limpio)
        if corte:
            # lista enumerada de documentos sin encabezado «Requisitos» (puede tener «Nota:» intercaladas)
            antes, lista, despues = corte
            p = partes(antes) if antes else {}
            p["requisitos"] = lista + (("\n\n" + despues) if despues else "")
    if set(p) == {"otro"} and re.search(r"procedimiento|flujo|proceso", nombre, re.I):
        p = {"procedimiento": p["otro"]}
    req = p.get("requisitos", "")
    n_req = cuenta_requisitos(req) if req else 0
    secciones = {TITULOS[k]: p[k] for k in ORDEN if k in p and (k != "para_que" or para)}
    if "para_que" in p and p["para_que"] != para:
        secciones[TITULOS["para_que"]] = para
    return {"secciones": secciones, "para_que": para, "requisitos": n_req, "formulario": es_formulario(limpio)}


def para_que_de_pagina(secciones, titulo):
    """Busca en las secciones de una página web el texto que dice para qué sirve el trámite."""
    t_norm = _sin_tildes(re.sub(r"\W+", " ", titulo)).strip()
    for k, v in secciones.items():
        if k.startswith(TITULOS["para_que"]) or re.match(rf"^({PARTES[0][2]})", _sin_tildes(k), re.I):
            v_norm = _sin_tildes(re.sub(r"\W+", " ", v)).strip()
            if v_norm and v_norm != t_norm and len(v_norm) > len(t_norm) + 15:
                return v.strip()
    for k, v in secciones.items():
        if k.startswith(("Requisitos", "Documento")):
            continue
        frases = _frases_para(v, 2)
        if frases:
            return "\n".join(frases)
    # página del trámite: el párrafo con que abre la página explica de qué se trata
    for k, v in secciones.items():
        if k.endswith(("(según el documento)", "(según el documento oficial)", "del documento")) or " — " in k \
                or re.search(r"requisit|documento", k, re.I):
            continue
        primero = next((l for l in v.split("\n") if l.strip()), "")
        if len(primero) >= 80 and not _ITEM.match(primero) and "requisit" not in primero[:40].lower():
            return primero.strip()
        break
    return ""


def tiene_requisitos_pagina(secciones):
    for k, v in secciones.items():
        if not k.endswith(("(según el documento)", "del documento")) and _lista_requisitos(v):
            return True
        if re.search(r"requisit", k, re.I) and cuenta_requisitos(v) >= 1 and len(v) >= 30:
            return True
        if re.search(r"(^|\n)\s*requisit[^\n]{0,80}\n(\s*(\d{1,2}[.)-]|[-•·*])[^\n]+\n?){2,}", v, re.I):
            return True
    return False
