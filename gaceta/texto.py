"""Limpieza del texto de La Gaceta y separación por acto. Solo texto: no descarga ni lee PDF.

Entrada: el texto de cada página tal como lo entrega gaceta.sonda.texto_columnas (columna izquierda
y luego derecha). Salida: los actos de la Sección A con su texto corrido, sin encabezados de página,
sin el recuadro del sumario y sin la Sección B. Nada se resume ni se completa: lo que no aparece en
la fuente se escribe "No consta en la fuente".
"""
import hashlib
import re

NO_CONSTA = "No consta en la fuente"
INICIO, FIN = "<!-- portal:inicio -->", "<!-- portal:fin -->"
CARPETA = "11 Normativa"
MAYUS = "A-ZÁÉÍÓÚÑÜ"

RE_CAB = re.compile(
    r"^(?:L?a Gaceta|Secci[óo]n\s+[AB]\s+(?:Acuerdos y Leyes|Avisos Legales)"
    r"|REP[ÚU]BLICA\s+DE\s+HONDURAS\s*-\s*TEGUCIGALPA.{0,70}No\.\s*[\d,. ]+\S{0,2})$")
RE_SEC_B = re.compile(r"^Secci[óo]n\s+B\s+Avisos Legales")
RE_ACTO = re.compile(
    rf"^(?:CERTIFICACI[ÓO]N,?\s+)?(DECRETO|ACUERDO|RESOLUCI[ÓO]N|CERTIFICACI[ÓO]N)"
    # calificativo: EJECUTIVO, MINISTERIAL, C.G., S.D.N., /SENASA... (palabras completas, nunca NÚMERO)
    rf"((?:[ /](?!N[ÚU]MERO\b|No\b)[{MAYUS}][{MAYUS}.]*(?=[\s/]|$)){{0,3}})\s*[-–]?\s*"
    rf"(No\.?|N[ÚU]MERO(?:\s+No\.?)?|N[°º]\.?)?[\s.\-–]*"
    # número: 034-2023, SEN-026-2021, PCM 20-2025, PCM- 055-2020, J.D. 001-05-02-2020
    rf"((?:[A-Z][A-Z.]*(?:-\s?|\s)(?=\d))?[A-Z0-9][\w\-/]*(?:\.\d+)?)\s*"
    rf"(?:[.\-]+(?:\s*Sesi[óo]n.*)?)?(?:\s+DEL?\s+[{MAYUS} ]+)?$")
RE_NUM_SOLO = re.compile(r"(?:[A-Z][A-Z.]*-)?\d\w*[-/][\w\-/]*\d")


def numero_acto(m):
    """Número del encabezado normalizado: «PCM 20-2025» y «PCM- 20-2025» -> «PCM-20-2025»."""
    return re.sub(r"(?<=[A-Z.])(?:-\s|\s)(?=\d)", "-", m.group(4)).rstrip(".-")


RE_CERT = re.compile(r"^CERTIFICACI[ÓO]N\.?$")
RE_SUSCRITO = re.compile(r"^(?:El|La)\s+(?:infrascrit|suscrit)[oa]")
RE_SUM = re.compile(r"(Decreto|Acuerdo|Resoluci[óo]n|Certificaci[óo]n)[\w ]*?\s(?:No\.?|N[úu]mero)\s*([A-Z0-9][\w\-/]*)")
RE_MARCA = re.compile(r"(?:\d{1,3}[.)]|[a-zñ][.)]|[•●▪■])")
RE_AUTORIDAD = re.compile(rf"^(?:(?:EL|LA|LOS|LAS) [{MAYUS}]{{3,}}|CONSIDERANDO|RESULTA)")
RE_EMISOR = re.compile(
    r"^(?:Poder|Presidencia|Secretar[íi]a|Instituto|Banco|Comisi[óo]n|Direcci[óo]n|Corte|Tribunal|Ministerio"
    r"|Congreso|Empresa|Servicio|Consejo|Procuradur[íi]a|Agencia|Superintendencia|Universidad|Municipalidad"
    r"|Alcald[íi]a|Registro|Fondo|Administraci[óo]n|Patronato|Aduanas)\b")
RE_ARRANQUE = re.compile(
    rf"^(?:CONSIDERANDO|POR TANTO|Por Tanto|ART[ÍI]CULO|Art[íi]culo|ACUERDA|A C U E R D A|DECRETA|D E C R E T A"
    rf"|RESUELVE|R E S U E L V E|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO"
    rf"|COMUN[ÍI]QUESE|PUBL[ÍI]QUESE|NOTIF[ÍI]QUESE|C[ÚU]MPLASE|Dado\s+en|CAP[ÍI]TULO|T[ÍI]TULO|SECCI[ÓO]N|CL[ÁA]USULA"
    rf"|[•●▪■\-–]\s|\d{{1,3}}[.)]\s|\d{{1,3}}\.\d{{1,3}}\.?\s|[a-zñ][.)]\s|[IVXL]{{1,5}}[.)]\s|\(\w{{1,3}}\)\s)")
RE_ARTICULO = re.compile(r"^(ART[ÍI]CULO|Art[íi]culo)\s+(\d+[\w\-]*|[A-ZÁÉÍÓÚ]{3,})\s*[.:\-–°º]")
TIPOS = {"DECRETO": ("Decreto", "Decretos"), "ACUERDO": ("Acuerdo", "Acuerdos"),
         "RESOLUCION": ("Resolución", "Resoluciones"), "CERTIFICACION": ("Certificación", "Certificaciones")}


def _sin_tildes(s):
    return s.translate(str.maketrans("ÁÉÍÓÚáéíóú", "AEIOUaeiou"))


def _compacto(s):
    return re.sub(r"[\s.]+", "", _sin_tildes(s or "")).upper()


def limpiar_paginas(paginas):
    """paginas: lista de textos (uno por página del PDF). Devuelve la lista de renglones de la
    Sección A como (número de página A, renglón) y un resumen de páginas."""
    renglones, pag_a, pag_b = [], 0, 0
    for i, texto in enumerate(paginas):
        lin = [re.sub(r"[ \t ]+", " ", x).strip() for x in texto.split("\n")]
        lin = [x for x in lin if x]
        es_b = i > 0 and (any(RE_SEC_B.match(x) for x in lin) or ("B." in lin and "A." not in lin))
        if es_b:
            pag_b += 1
            continue
        pag_a += 1
        if i == 0:
            lin = _portada(lin)
        if i == 1:
            lin = _recuadro(lin, r"^DIARIO OFICIAL DE LA REP", r"^CENTRO C[ÍI]VICO GUBERNAMENTAL")
        k = next((k for k, x in enumerate(lin) if x.startswith("El Diario Oficial La Gaceta circula")), None)
        if k is not None and any("Suscripciones" in x for x in lin[k:k + 6]):
            lin = lin[:k]  # recuadro de suscripciones de la contraportada
        fuera = set()
        for k, x in enumerate(lin):
            if RE_CAB.match(x):
                fuera.add(k)
            elif x in ("A.", "B."):
                fuera.add(k)
                for v in (k - 1, k + 1):
                    if 0 <= v < len(lin) and re.fullmatch(r"\d{1,4}", lin[v]):
                        fuera.add(v)
        renglones += [(pag_a, x) for k, x in enumerate(lin) if k not in fuera]
    return renglones, {"paginas_a": pag_a, "paginas_b": pag_b}


def _recuadro(lin, ini, fin):
    a = next((k for k, x in enumerate(lin) if re.match(ini, x)), None)
    b = next((k for k, x in enumerate(lin) if re.match(fin, x)), None)
    if a is None or b is None or b < a:
        return lin
    return lin[:a] + lin[b + 1:]


def _portada(lin):
    """Quita de la primera página la cabecera del diario y el recuadro del sumario."""
    k = next((k for k, x in enumerate(lin) if re.search(r"NUM\.\s*[\d,. ]+$", x)), None)
    if k is not None:
        lin = lin[k + 1:]
    if lin and re.fullmatch(r"Secci[óo]n\s+A", lin[0]):
        lin = lin[1:]
    fin = next((k for k, x in enumerate(lin) if x.startswith("Desprendible para su comodidad")), None)
    if fin is not None:
        ini = next((k for k, x in enumerate(lin[:fin]) if re.fullmatch(r"SUMARIO|Secci[óo]n\s+A", x)), None)
        if ini is not None:
            lin = lin[:ini] + lin[fin + 1:]
    return lin


def _mayus(x):
    letras = [c for c in x if c.isalpha()]
    return len(letras) >= 3 and all(c.isupper() for c in letras)


def parrafos(lineas):
    """Une los renglones cortados por la columna en párrafos corridos."""
    out = []
    for x in lineas:
        if not out:
            out.append(x)
            continue
        p = out[-1]
        if RE_MARCA.fullmatch(p):  # marcador de lista solo en su renglón
            out[-1] = p + " " + x
            continue
        nuevo = bool(RE_ARRANQUE.match(x) or RE_ACTO.match(x) or RE_MARCA.fullmatch(x))
        if not nuevo and p[-1] in ".:;" and not x[0].islower():
            nuevo = True
        if not nuevo and _mayus(p) and not _mayus(x) and len(p) < 60 and p[-1] != "," and not x[0].islower():
            nuevo = True
        if not nuevo and _mayus(x) and not _mayus(p) and len(p) < 40 and p[-1] != ",":
            nuevo = True
        if re.fullmatch(r"(?:ART[ÍI]CULO|Art[íi]culo)\s+\S+?[.:\-–]*", p):
            nuevo = False
        if nuevo:
            out.append(x)
        elif re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]-$", p) and x[0].isalpha() and p[-2].isupper() == x[0].isupper():
            out[-1] = p[:-1] + x
        else:
            out[-1] = p + " " + x
    return out


def leer_sumario(sumario):
    """['PODER LEGISLATIVODecreto No. 196-2026', ...] -> [{'emisor', 'detalle'}]."""
    res = []
    for s in sumario or []:
        m = re.match(rf"^([{MAYUS} ,.\-()]+?)(?=[{MAYUS}][a-záéíóúñ])", s)
        res.append({"emisor": m.group(1).strip(" ,.-") if m else "", "detalle": s[m.end():].strip() if m else s})
    return res


def separar_actos(renglones, sumario):
    """Corta la Sección A en actos. Un encabezado cuenta como inicio de acto si su número está en el
    sumario o si lo sigue la autoridad que lo emite (o un CONSIDERANDO)."""
    entradas = leer_sumario(sumario)
    todo = _compacto(" ".join(sumario or []))
    lin = [x for _, x in renglones]
    cortes = []
    for k, x in enumerate(lin):
        if RE_CERT.match(x) and k + 1 < len(lin) and RE_SUSCRITO.match(lin[k + 1]):
            cortes.append((k, None, ""))
            continue
        m = RE_ACTO.match(x)
        if not m or len(x) > 90 or (not m.group(3) and not RE_NUM_SOLO.fullmatch(numero_acto(m))):
            continue
        num = numero_acto(m)
        if cortes and cortes[-1][2] == num and k - cortes[-1][0] < 15:
            continue
        cerca = [y for y in lin[k + 1:k + 5]]
        if _compacto(num) in todo or any(RE_AUTORIDAD.match(y) for y in cerca):
            cortes.append((k, m, num))
    actos = []

    def emisor_impreso(k):
        for j in range(k - 1, max(k - 5, -1), -1):
            if RE_ACTO.match(lin[j]) or lin[j][-1] in ".;:,":
                break
            if RE_EMISOR.match(lin[j]) and all(len(y) < 60 for y in lin[j:k]):
                return j
        return None

    limites = []
    for k, m, num in cortes:
        j = emisor_impreso(k)
        limites.append((j if j is not None else k, k, m, num))
    primero = limites[0][0] if limites else len(lin)
    if len(" ".join(lin[:primero])) > 300:
        det = "; ".join(e["detalle"] for e in entradas) if not limites else ""
        ms = RE_SUM.search(det) if len(entradas) == 1 and not limites else None
        tipo, carpeta = TIPOS[_sin_tildes(ms.group(1)).upper()] if ms else ("Otro acto", "Otros actos")
        actos.append({"tipo": tipo, "carpeta": carpeta, "numero": ms.group(2).rstrip(".-") if ms else "", "titulo": "",
                      "emisor": (entradas[0]["emisor"] if entradas and not limites else ""), "sumario": det,
                      "desde": 0, "hasta": primero})
    for n, (ini, k, m, num) in enumerate(limites):
        fin = limites[n + 1][0] if n + 1 < len(limites) else len(lin)
        tipo, carpeta = TIPOS[_sin_tildes(m.group(1))] if m else TIPOS["CERTIFICACION"]
        if num:
            ent = next((e for e in entradas if _compacto(num) in _compacto(e["detalle"])), None)
        else:
            ent = next((e for e in entradas if e["detalle"].startswith("Certificaci")), None)
        emisor = " ".join(lin[ini:k]) if ini < k else (ent["emisor"] if ent else "")
        actos.append({"tipo": tipo, "carpeta": carpeta, "numero": num, "titulo": lin[k], "emisor": emisor,
                      "sumario": ent["detalle"] if ent else "", "desde": k + 1, "hasta": fin})
    for a in actos:
        tramo = renglones[a["desde"]:a["hasta"]]
        a["parrafos"] = parrafos([x for _, x in tramo])
        pags = [p for p, _ in tramo] or [0]
        a["paginas"] = f"A. {pags[0]}" + (f" - {pags[-1]}" if pags[-1] != pags[0] else "")
        del a["desde"], a["hasta"]
    return [a for a in actos if a["parrafos"]]


# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------
def _yaml(v):
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _archivo(s):
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|#^\[\]]', "-", s)).strip(" .-")[:120]


MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]


def ruta_anio(anio):
    return f"{CARPETA}/La Gaceta/La Gaceta {anio}.md"


def ruta_mes(fecha):
    return f"{CARPETA}/La Gaceta/{fecha[:4]}/{fecha[:7]} {MESES[int(fecha[5:7]) - 1]}.md"


def ruta_edicion(ed):
    return f"{CARPETA}/La Gaceta/{ed['fecha'][:4]}/La Gaceta {ed['numero']} ({ed['fecha']}).md"


def ruta_acto(ed, a, usadas):
    base = f"{a['tipo']} {a['numero']}".strip() if a["tipo"] != "Otro acto" else "Otros actos"
    nombre = _archivo(f"{base} (Gaceta {ed['numero']})")
    ruta, n = f"{CARPETA}/{a['carpeta']}/{ed['fecha'][:4]}/{nombre}.md", 2
    while ruta in usadas:
        ruta, n = f"{CARPETA}/{a['carpeta']}/{ed['fecha'][:4]}/{nombre} {n}.md", n + 1
    usadas.add(ruta)
    return ruta


def _cuerpo_texto(pars):
    out = []
    for p in pars:
        m = RE_ARTICULO.match(p)
        if m:
            out.append(f"#### Artículo {m.group(2)}")
        if re.match(r"^(#|>|\||={3,}|-{3,}$|\d+\)\s)", p):
            p = "\\" + p
        out.append(p.replace("<", "&lt;"))
    return "\n\n".join(out)


def nota_acto(ed, a, hoy):
    texto = _cuerpo_texto(a["parrafos"])
    huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
    titulo = a["titulo"] or (f"Según el sumario de La Gaceta: {a['sumario']}" if a["sumario"] else NO_CONSTA)
    enlace = f"[[{ruta_edicion(ed)[:-3]}|La Gaceta {ed['numero']}]]"
    props = [("tipo", "norma"), ("tipo_acto", a["tipo"]), ("numero", a["numero"] or NO_CONSTA), ("titulo", titulo),
             ("emisor", a["emisor"] or NO_CONSTA), ("gaceta_numero", ed["numero"]), ("gaceta_fecha", ed["fecha"]),
             ("gaceta", enlace), ("paginas", a["paginas"]), ("sumario", a["sumario"] or NO_CONSTA),
             ("url_pdf", ed["descarga"]), ("extraido", hoy), ("huella", huella)]
    fm = "\n".join(f"{k}: {_yaml(v)}" for k, v in props)
    cab = [("Tipo de acto", a["tipo"]), ("Número", a["numero"] or NO_CONSTA), ("Emisor", a["emisor"] or NO_CONSTA),
           ("Publicado en", f"{enlace.replace('|', chr(92) + '|')} del {ed['fecha']}"), ("Páginas", a["paginas"]),
           ("Según el sumario de La Gaceta", a["sumario"] or NO_CONSTA)]
    tabla = "| Dato | Valor |\n| --- | --- |\n" + "\n".join(f"| {k} | {str(v).replace('|', chr(92) + '|') if k != 'Publicado en' else v} |" for k, v in cab)
    return (f"---\n{fm}\n---\n{INICIO}\n# {titulo}\n\n{tabla}\n\n## Texto\n\n{texto}\n\n## Fuente\n\n"
            f"Texto extraído del PDF de La Gaceta No. {ed['numero']} del {ed['fecha']}, publicado por la ENAG: "
            f"{ed['descarga']}. Copia de consulta; el texto oficial es el del PDF.\n{FIN}\n\n## Notas propias\n\n")


def nota_edicion(ed, actos, rutas, resumen, hoy):
    props = [("tipo", "gaceta"), ("gaceta_numero", ed["numero"]), ("gaceta_fecha", ed["fecha"]),
             ("paginas_seccion_a", resumen["paginas_a"]), ("paginas_seccion_b", resumen["paginas_b"]),
             ("actos", len(actos)), ("url_pdf", ed["descarga"]), ("url_detalle", ed.get("detalle") or NO_CONSTA),
             ("extraido", hoy)]
    fm = "\n".join(f"{k}: {_yaml(v)}" for k, v in props)
    sumario = "\n".join(f"- {s}" for s in ed.get("sumario") or []) or NO_CONSTA
    lista = "\n".join(f"- [[{r[:-3]}|{a['titulo'] or 'Otros actos'}]] ({a['paginas']})" for a, r in zip(actos, rutas))
    return (f"---\n{fm}\n---\n{INICIO}\n# La Gaceta No. {ed['numero']} del {ed['fecha']}\n\n"
            f"{enlace_mes(ed['fecha'])}\n\n## Sumario según el portal de la ENAG\n\n{sumario}\n\n"
            f"## Actos de la Sección A\n\n{lista or 'No se identificaron actos en la Sección A.'}\n\n"
            f"La Sección B (Avisos Legales) no se copia.\n\n## Fuente\n\n{ed['descarga']}\n{FIN}\n\n## Notas propias\n\n")


def enlace_mes(fecha):
    return f"[[{ruta_mes(fecha)[:-3]}|{MESES[int(fecha[5:7]) - 1]} de {fecha[:4]}]]"


def notas_indice(ediciones):
    """ediciones: lista de (fecha, numero, ruta, actos). Devuelve {ruta: contenido} con el índice general,
    una nota por año y una por mes, para que el grafo quede en árbol: índice, año, mes, edición, acto."""
    notas, anios = {}, {}
    for e in sorted(ediciones):
        anios.setdefault(e[0][:4], {}).setdefault(e[0][:7], []).append(e)
    cuerpo = ["# Índice de normativa", "", "[[00 Panel/Directorio|Directorio de Case Deck]]", "",
              "Normas publicadas en la Sección A de La Gaceta, por año.", ""]
    for anio in sorted(anios, reverse=True):
        meses = anios[anio]
        total = sum(len(v) for v in meses.values())
        cuerpo.append(f"- [[{ruta_anio(anio)[:-3]}|La Gaceta {anio}]] ({total} ediciones cargadas)")
        lin = [f"# La Gaceta {anio}", "", f"[[{CARPETA}/Índice de normativa|Índice de normativa]]", ""]
        for mes in sorted(meses, reverse=True):
            eds = sorted(meses[mes], reverse=True)
            lin.append(f"- {enlace_mes(mes + '-01')} ({len(eds)} ediciones)")
            lm = [f"# {MESES[int(mes[5:7]) - 1]} de {anio}", "", f"[[{ruta_anio(anio)[:-3]}|La Gaceta {anio}]]", "",
                  "| Fecha | Edición | Actos de la Sección A |", "| --- | --- | --- |"]
            lm += [f"| {f} | [[{r[:-3]}\\|La Gaceta {n}]] | {a} |" for f, n, r, a in eds]
            notas[ruta_mes(mes + "-01")] = ('---\ntipo: "normativa_mes"\n---\n'
                                           f"{INICIO}\n" + "\n".join(lm) + f"\n{FIN}\n")
        notas[ruta_anio(anio)] = ('---\ntipo: "normativa_anio"\n---\n'
                                  f"{INICIO}\n" + "\n".join(lin) + f"\n{FIN}\n")
    notas[f"{CARPETA}/Índice de normativa.md"] = ('---\ntipo: "normativa_indice"\n---\n' + f"{INICIO}\n"
                                                + "\n".join(cuerpo) + f"\n{FIN}\n")
    return notas
