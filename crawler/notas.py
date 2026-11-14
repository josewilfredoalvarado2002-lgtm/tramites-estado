"""Convierte las fichas leídas del portal en notas Markdown para Obsidian.

Todo lo que genera el crawler va entre los marcadores portal:inicio y portal:fin.
La sección "Notas propias" queda debajo y el crawler nunca la toca.
"""
import hashlib
import json
import os
import re

from .portal import NO_CONSTA, URL_FICHA, campos, json_canonico

CARPETA_RAIZ = "10 Trámites del Estado"
CARPETA_SISTEMA = CARPETA_RAIZ + "/_Sistema"
INICIO = "<!-- portal:inicio -->"
FIN = "<!-- portal:fin -->"
NOTAS_PROPIAS = "## Notas propias"
ENLACE_CASE_DECK = "[[00 Panel/Directorio|Directorio de Case Deck]]"
VIGENTE = "Vigente"
YA_NO_APARECE = "Ya no aparece en el portal"
SIN_RESOLVER = "No se pudo verificar en la extracción"

# Propiedades que administra el crawler. El puente reemplaza solo estas y conserva las que agregués.
PROPIEDADES_TRAMITE = [
    "tipo", "id_portal", "titulo", "aliases", "institucion", "responsable", "modalidad", "dirigido_a",
    "costo", "tiempo_respuesta", "comparador_tiempo_dias", "comparador_complejidad", "url_ficha", "url_inicio", "actualizado_portal", "extraido", "huella",
    "estado_portal", "no_aparece_desde",
]
PROPIEDADES_INSTITUCION = ["tipo", "nombre", "siglas_comparador", "id_portal_institucion", "url_listado", "tramites_en_portal"]


# ---------------------------------------------------------------------------
# Nombres de archivo
# ---------------------------------------------------------------------------
def limpiar_nombre(nombre: str, maximo=120) -> str:
    """Quita los caracteres que Obsidian no admite en nombres de archivo o que rompen enlaces."""
    limpio = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", nombre or "")
    limpio = re.sub(r"\s{2,}", " ", limpio).strip().strip(".")
    if len(limpio) > maximo:
        limpio = limpio[:maximo].rsplit(" ", 1)[0].strip()
    return limpio or "Sin nombre"


def nombre_nota_tramite(id_portal, titulo) -> str:
    return limpiar_nombre(f"TR-{id_portal} {titulo}")


def nombre_nota_institucion(nombre) -> str:
    return limpiar_nombre(nombre)


def enlace(carpeta, nota, texto) -> str:
    """Enlace con la ruta completa: evita que Obsidian lo confunda con otra nota del mismo nombre
    (por ejemplo, una institución con el mismo nombre en 20 Despacho/Catálogos/Instituciones)."""
    visible = re.sub(r"[\[\]|]", " ", texto or nota).strip()
    return f"[[{carpeta}/{nota}|{visible}]]"


# ---------------------------------------------------------------------------
# Escritura segura de texto del portal en Markdown
# ---------------------------------------------------------------------------
def md(texto: str) -> str:
    """Evita que el texto del portal se convierta en enlaces, etiquetas o HTML de Obsidian.
    No cambia palabras; solo antepone barras de escape donde hace falta."""
    t = texto.replace("\\", "\\\\")
    t = t.replace("<", "\\<").replace("[[", "\\[\\[").replace("]]", "\\]\\]").replace("%%", "\\%\\%")
    t = t.replace("==", "\\=\\=")
    t = re.sub(r"(^|\s)#(?=[^\s#])", r"\1\\#", t)
    return t


def md_parrafo(texto: str) -> str:
    t = md(texto)
    # un renglón que empieza como lista, cita o título se escapa para que se lea tal cual
    return re.sub(r"^(\s*)([-+*>]|#{1,6}\s|\d+[.)])", lambda m: m.group(1) + "\\" + m.group(2), t)


def celda(texto: str) -> str:
    return md(texto).replace("|", "\\|")


def enlace_md(texto: str, url: str) -> str:
    """Enlace externo en Markdown. Los corchetes del texto se escapan para que Obsidian no los lea como [[enlace interno]]."""
    marcado = (texto or url).replace("[", "\ue000").replace("]", "\ue001")
    t = celda(marcado).replace("\ue000", "\\[").replace("\ue001", "\\]")
    destino = f"<{url}>" if any(c in url for c in " ()<>") else url
    return f"[{t}]({destino})"


def yaml_texto(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def frontmatter(props: list) -> str:
    """props: lista de (clave, valor). Valores: str, int, lista de str o None (se omite)."""
    L = ["---"]
    for k, v in props:
        if v is None:
            continue
        if isinstance(v, list):
            L.append(f"{k}:")
            L += [f"  - {yaml_texto(x)}" for x in v]
        elif isinstance(v, bool):
            L.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            L.append(f"{k}: {v}")
        elif isinstance(v, Crudo):
            L.append(f"{k}: {v}")
        else:
            L.append(f"{k}: {yaml_texto(v)}")
    L.append("---")
    return "\n".join(L)


class Crudo(str):
    """Valor que se escribe sin comillas (fechas)."""


# ---------------------------------------------------------------------------
# Huellas
# ---------------------------------------------------------------------------
def sha(obj) -> str:
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


def secciones(ficha, url_final, comparador=None) -> dict:
    """Huella de cada sección visible, con el nombre que usa el portal."""
    s = {
        "Cabecera": sha({k: ficha.get(k) for k in ("titulo", "institucion", "modalidad", "numero", "etiquetas", "accion")}),
        "Descripción": sha(ficha.get("descripcion")),
        "URL final del botón": sha(url_final),
        "Según el comparador del portal": sha(comparador),
    }
    for d in ficha["datos"]:
        s[d["titulo"] or "Dato sin rótulo"] = sha(d["lineas"])
    for p in ficha["pestanas"]:
        s[p["etiqueta"] or p["clave"]] = sha(p["contenido"])
    return s


def huella(ficha, url_final, comparador=None) -> str:
    return sha({"ficha": ficha, "url_final_accion": url_final, "comparador": comparador})


# ---------------------------------------------------------------------------
# Nota del trámite
# ---------------------------------------------------------------------------
def _lista_texto(lineas_):
    return "\n".join(md_parrafo(x) for x in lineas_) if lineas_ else NO_CONSTA


def _render_contenido(c) -> list:
    L = []
    if c["tipo"] == "lista":
        if not c["elementos"]:
            return [NO_CONSTA]
        numerada = all(e["marca"].isdigit() for e in c["elementos"])
        for i, e in enumerate(c["elementos"], 1):
            vineta = f"{e['marca']}." if numerada else "-"
            texto = " ".join(e["texto"]) if e["texto"] else NO_CONSTA
            L.append(f"{vineta} {md(texto)}")
            sang = " " * (len(vineta) + 1)
            for par in e["meta"]:
                valor = "; ".join(par["valor"]) if par["valor"] else NO_CONSTA
                L.append(f"{sang}- {md(par['etiqueta'] or 'Dato')}: {md(valor)}")
            for u in e["documentos"]:
                L.append(f"{sang}- Documento enlazado en el portal: {u}")
            for en in e["enlaces"]:
                L.append(f"{sang}- Enlace en el texto: {enlace_md(en['texto'], en['url'])}")
            for o in e["otros"]:
                L.append(f"{sang}- {md(o)}")
        return L
    if c["tipo"] == "lugares":
        if not c["lugares"]:
            return [NO_CONSTA]
        for lug in c["lugares"]:
            L.append(f"### {md(' '.join(lug['titulo'])) if lug['titulo'] else 'Lugar sin nombre en el portal'}")
            L.append("")
            vistos = set()
            for d in lug["datos"]:
                vistos.add(d["etiqueta"].lower())
                valor = "; ".join(d["valor"]) if d["valor"] else NO_CONSTA
                L.append(f"- {md(d['etiqueta'] or 'Dato')}: {md(valor)}")
            for en in lug["enlaces"]:
                L.append(f"- Enlace: {enlace_md(en['texto'], en['url'])}")
            # datos que se esperan en un lugar y que el portal no muestra
            if not any(k.startswith("horario") for k in vistos):
                L.append(f"- Horario: {NO_CONSTA}")
            if not lug["enlaces"] and not any("mapa" in k for k in vistos):
                L.append(f"- Enlace de mapa: {NO_CONSTA}")
            L.append("")
        return L[:-1] if L and L[-1] == "" else L
    if c["tipo"] == "tabla":
        if not c["filas"]:
            return [NO_CONSTA]
        enc = [h for h in c["encabezados"] if h.lower() not in ("acción", "accion")] or c["encabezados"]
        idx = [i for i, h in enumerate(c["encabezados"]) if h in enc]
        L.append("| " + " | ".join(celda(h) for h in enc) + " |")
        L.append("| " + " | ".join("---" for _ in enc) + " |")
        for f in c["filas"]:
            celdas = [f["celdas"][i] if i < len(f["celdas"]) else "" for i in idx]
            L.append("| " + " | ".join(celda(x) for x in celdas) + " |")
        return L
    if not c.get("lineas"):
        return [NO_CONSTA]
    L += [md_parrafo(x) for x in c["lineas"]]
    for en in c.get("enlaces", []):
        L.append(f"- {enlace_md(en['texto'], en['url'])}")
    return L


def render_tramite(ficha, enlace_institucion, extraido, url_final, url_final_error,
                   comparador=None, comparador_error=None, estado_portal=VIGENTE, no_aparece_desde=None) -> str:
    """Devuelve la nota completa (propiedades, bloque del portal y sección Notas propias vacía).
    comparador: datos de la función «Comparar trámites» del portal, o None si no se pudieron consultar."""
    c = campos(ficha)
    h = huella(ficha, url_final, comparador)
    comp = comparador or {}
    dias = comp.get("tiempo_estimado_dias")
    id_ = ficha["id_portal"]
    props = [
        ("tipo", "tramite"),
        ("id_portal", id_),
        ("titulo", ficha["titulo"]),
        ("aliases", [ficha["titulo"]]),
        ("institucion", enlace_institucion),
        ("responsable", c["responsable"]),
        ("modalidad", c["modalidad"]),
        ("dirigido_a", c["dirigido_a"]),
        ("costo", c["costo"]),
        ("tiempo_respuesta", c["tiempo_respuesta"]),
        ("comparador_tiempo_dias", dias if isinstance(dias, int) and not isinstance(dias, bool) else None),
        ("comparador_complejidad", comp.get("nivel_complejidad") or None),
        ("url_ficha", URL_FICHA.format(id=id_)),
        ("url_inicio", c["url_inicio"]),
        ("actualizado_portal", c["actualizado_portal"]),
        ("extraido", Crudo(extraido)),
        ("huella", h),
        ("estado_portal", estado_portal),
        ("no_aparece_desde", Crudo(no_aparece_desde) if no_aparece_desde else None),
    ]
    acc = ficha.get("accion")
    if url_final:
        final = url_final
    elif acc and url_final_error:
        final = SIN_RESOLVER
    else:
        final = NO_CONSTA
    B = [INICIO, f"# {md(ficha['titulo'])}", ""]
    if estado_portal != VIGENTE:
        B += [f"> [!warning] {estado_portal} desde el {no_aparece_desde}. Se conserva la última versión extraída.", ""]
    B += [
        f"> [!info] Copia de la ficha N.º {id_} del Portal de Trámites del Estado de Honduras, tal como aparece en el portal. "
        "No se resumió, completó ni verificó. El crawler reescribe este bloque cuando el portal cambia; tus anotaciones van en Notas propias.",
        "",
        "## Cabecera",
        "",
        "| Dato | Según el portal |",
        "| --- | --- |",
        f"| Título | {celda(ficha['titulo'])} |",
        f"| Institución | {celda(ficha['institucion'] or NO_CONSTA)} |",
        f"| N.º | {celda(ficha.get('numero') or NO_CONSTA)} |",
        f"| Modalidad | {celda(c['modalidad'])} |",
        f"| Etiquetas de la ficha | {celda(', '.join(ficha['etiquetas']) or NO_CONSTA)} |",
        f"| Botón de acción | {celda(acc['texto']) if acc else NO_CONSTA} |",
        f"| URL del botón | {celda(acc['url']) if acc and acc['url'] else NO_CONSTA} |",
        f"| URL final del botón (después de redirecciones) | {celda(final)} |",
        "",
        "## Descripción",
        "",
        _lista_texto(ficha["descripcion"]),
        "",
    ]
    for d in ficha["datos"]:
        B += [f"## {md(d['titulo'] or 'Dato sin rótulo')}", "", _lista_texto(d["lineas"]), ""]
    for p in ficha["pestanas"]:
        B += [f"## {md(p['etiqueta'] or p['clave'])}", ""]
        B += _render_contenido(p["contenido"])
        B.append("")
        if p["clave"] == "enlaces":
            B.append(f"- Marco legal: {_texto_o_no_consta(c['marco_legal'])}")
            B.append(f"- Costos o tasas: {md(c['costo'])}")
            B.append(f"- Tiempo de respuesta: {md(c['tiempo_respuesta'])}")
            B.append("")
    if not any(p["clave"] == "enlaces" for p in ficha["pestanas"]):
        B += ["## Más información", "", NO_CONSTA, "",
              f"- Marco legal: {_texto_o_no_consta(c['marco_legal'])}",
              f"- Costos o tasas: {md(c['costo'])}",
              f"- Tiempo de respuesta: {md(c['tiempo_respuesta'])}", ""]
    B += ["## Según el comparador del portal", "",
          "> [!note] Datos que el portal muestra en su función «Comparar trámites», no en la ficha. "
          "El portal no explica cómo los calcula; se copian tal como los entrega.", ""]
    if comparador is None:
        B.append("No se pudo consultar el comparador en la extracción." if comparador_error else NO_CONSTA)
    else:
        def v(x, sufijo=""):
            return NO_CONSTA.replace("portal", "comparador") if x in (None, "") else f"{md(str(x))}{sufijo}"
        B += [f"- Tiempo estimado: {v(dias, ' días' if dias != 1 else ' día')}",
              f"- Nivel de complejidad: {v(comp.get('nivel_complejidad'))}",
              f"- Puntaje de complejidad: {v(comp.get('puntaje_complejidad'))}",
              f"- Siglas de la institución: {v(comp.get('siglas_institucion'))}"]
    B.append("")
    B += [
        "## Fuente",
        "",
        f"- Ficha: {URL_FICHA.format(id=id_)}",
        f"- Última actualización según el portal: {md(c['actualizado_portal'])}",
        f"- Fecha y hora de extracción: {extraido.replace('T', ' ')} (hora de Honduras, UTC-6)",
        FIN,
        "",
        NOTAS_PROPIAS,
        "",
    ]
    return frontmatter(props) + "\n" + "\n".join(B)


def _texto_o_no_consta(lineas_):
    return "; ".join(md(x) for x in lineas_) if lineas_ else NO_CONSTA


# ---------------------------------------------------------------------------
# Notas de institución, índice, base y reportes
# ---------------------------------------------------------------------------
def render_institucion(nombre, id_inst, url_listado, filas, siglas=None) -> str:
    """filas: lista de dicts con nota, titulo, id, modalidad, estado_portal, no_aparece_desde."""
    vigentes = sum(1 for f in filas if f["estado_portal"] == VIGENTE)
    props = [
        ("tipo", "institucion_portal"),
        ("nombre", nombre),
        ("siglas_comparador", siglas or None),
        ("id_portal_institucion", int(id_inst) if id_inst and str(id_inst).isdigit() else NO_CONSTA),
        ("url_listado", url_listado or NO_CONSTA),
        ("tramites_en_portal", vigentes),
    ]
    B = [INICIO, f"# {md(nombre)}", "",
         "> [!info] Institución tal como la nombra el Portal de Trámites del Estado. "
         "Para relacionarla con tu catálogo de Case Deck agregá la propiedad `catalogo_case_deck` con el enlace a su nota en 20 Despacho/Catálogos/Instituciones; "
         "el crawler no toca esa propiedad.", "",
         f"Siglas según el comparador del portal: {md(siglas) if siglas else NO_CONSTA.replace('portal', 'comparador')}.", "",
         f"## Trámites en el portal ({vigentes})", ""]
    for f in sorted(filas, key=lambda x: x["id"]):
        extra = "" if f["estado_portal"] == VIGENTE else f" · {f['estado_portal']} desde el {f['no_aparece_desde']}"
        B.append(f"- {enlace(os.path.dirname(f['ruta']), f['nota'], f['titulo'])} · N.º {f['id']} · {md(f['modalidad'] or NO_CONSTA)}{extra}")
    if not filas:
        B.append(NO_CONSTA)
    B += ["", FIN, "", NOTAS_PROPIAS, ""]
    return frontmatter(props) + "\n" + "\n".join(B)


def render_indice(instituciones) -> str:
    """instituciones: lista de (enlace_institucion, nombre, vigentes, desaparecidos)."""
    total = sum(v for _, _, v, _ in instituciones)
    B = ["---", "tipo: sistema", "---", "", "# Índice de trámites", "",
         "Consulta de los trámites que publica el Portal de Trámites del Estado de Honduras (DIGER), ordenados por institución. "
         "Es material de referencia y no forma parte del control de casos. Detalle de la última corrida en [[Última extracción]].", "",
         f"Trámites vigentes en el portal: {total}. Instituciones con trámites: {sum(1 for i in instituciones if i[2])}.", "",
         f"Conexión con el control de casos: {ENLACE_CASE_DECK}. Es el único enlace del índice hacia el resto de la bóveda, "
         "para que en la vista de grafo los trámites y Case Deck se vean como dos redes unidas por una línea.", "",
         "## Instituciones", ""]
    for enl, nombre, v, d in sorted(instituciones, key=lambda x: x[1].lower()):
        extra = f" · {d} ya no aparecen" if d else ""
        B.append(f"- {enl} · {v}{extra}")
    B += ["", "## Vista de base", "", "![[Trámites.base]]", ""]
    return "\n".join(B)


BASE_TRAMITES = """filters:
  and:
    - tipo == "tramite"
    - file.inFolder("10 Trámites del Estado")
properties:
  file.name:
    displayName: Nota
  id_portal:
    displayName: N.º
  titulo:
    displayName: Trámite
  institucion:
    displayName: Institución
  modalidad:
    displayName: Modalidad
  dirigido_a:
    displayName: Dirigido a
  responsable:
    displayName: Responsable
  costo:
    displayName: Costo
  tiempo_respuesta:
    displayName: Tiempo de respuesta
  comparador_tiempo_dias:
    displayName: Días estimados (comparador)
  comparador_complejidad:
    displayName: Complejidad (comparador)
  estado_portal:
    displayName: Estado en el portal
views:
  - type: table
    name: Por institución
    groupBy:
      property: institucion
      direction: ASC
    order:
      - id_portal
      - file.name
      - modalidad
      - dirigido_a
      - responsable
      - comparador_tiempo_dias
      - comparador_complejidad
      - estado_portal
    sort:
      - property: id_portal
        direction: ASC
  - type: table
    name: En línea
    filters:
      and:
        - modalidad == "En línea"
    groupBy:
      property: institucion
      direction: ASC
    order:
      - id_portal
      - file.name
      - dirigido_a
      - responsable
  - type: table
    name: Presencial
    filters:
      and:
        - modalidad == "Presencial"
    groupBy:
      property: institucion
      direction: ASC
    order:
      - id_portal
      - file.name
      - dirigido_a
      - responsable
  - type: table
    name: Dirigido a (texto contiene «natural»)
    filters:
      and:
        - dirigido_a.join(" ").lower().contains("natural")
    groupBy:
      property: institucion
      direction: ASC
    order:
      - id_portal
      - file.name
      - modalidad
      - dirigido_a
  - type: table
    name: Dirigido a (texto contiene «jurídic»)
    filters:
      and:
        - dirigido_a.join(" ").lower().contains("jurídic")
    groupBy:
      property: institucion
      direction: ASC
    order:
      - id_portal
      - file.name
      - modalidad
      - dirigido_a
  - type: table
    name: Ya no aparecen en el portal
    filters:
      and:
        - estado_portal == "Ya no aparece en el portal"
    order:
      - id_portal
      - file.name
      - institucion
      - no_aparece_desde
"""
