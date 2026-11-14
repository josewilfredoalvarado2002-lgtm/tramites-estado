"""
Exporta los trámites de San Pedro Sula como notas de Obsidian, con el mismo formato
que "10 Trámites del Estado": propiedades arriba, bloque del portal entre
<!-- portal:inicio --> y <!-- portal:fin -->, y "## Notas propias" que nunca se toca.
"""
import json
import os
import re
from datetime import datetime

INSTITUCION = "Municipalidad de San Pedro Sula"
INICIO, FIN = "<!-- portal:inicio -->", "<!-- portal:fin -->"
TITULOS_SECCION = {
    "descripcion": "Descripción",
    "documento_que_recibe": "Documento que recibe",
    "fundamento_juridico": "Fundamento jurídico",
    "requisitos": "Requisitos",
    "informacion_adicional": "Información adicional",
    "texto": "Contenido",
}


def q(texto):
    """Texto seguro para las propiedades (YAML)."""
    return json.dumps(texto or "No consta en el portal", ensure_ascii=False)


def nombre_archivo(texto, maximo=110):
    t = re.sub(r'[\\/:*?"<>|#^\[\]]', "", texto or "")
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:maximo].rstrip(" .") or "sin título"


def md(texto):
    """Evita que una línea del portal se convierta en encabezado o tabla por accidente."""
    lineas = []
    for l in (texto or "").split("\n"):
        if l.startswith(("#", "|", ">")):
            l = "\\" + l
        lineas.append(l)
    return "\n\n".join(x for x in lineas if x.strip())


def ruta_nota(carpeta, r):
    d = r["datos"]
    sub = "Preguntas frecuentes" if (d.get("categoria") or "").upper().startswith("PREGUNTA") else "Trámites"
    nombre = f"SPS-{r['codigo']} {nombre_archivo(d.get('titulo') or d.get('gestion'))}.md"
    return os.path.join(carpeta, sub, nombre)


def bloque_portal(r, ahora):
    d, s = r["datos"], r["datos"].get("secciones", {})
    titulo = d.get("titulo") or d.get("gestion")
    partes = [
        INICIO,
        f"# {titulo}",
        "",
        f"> [!info] Copia de la ficha N.º {r['codigo']} del Portal Informativo de Gestiones de la "
        f"{INSTITUCION}, tal como aparece en el portal. No se resumió, completó ni verificó. "
        "El crawler reescribe este bloque cuando el portal cambia; tus anotaciones van en Notas propias.",
        "",
        "## Cabecera",
        "",
        "| Dato | Según el portal |",
        "| --- | --- |",
    ]
    for etiqueta, valor in [
        ("Título", titulo), ("Institución", INSTITUCION), ("N.º", r["codigo"]),
        ("Gerencia", d.get("gerencia")), ("Unidad", d.get("unidad")),
        ("Categoría", d.get("categoria")), ("Tipo", d.get("tipo")),
        ("Costo", d.get("costo")), ("Vigencia", d.get("vigencia")),
        ("Tiempo de respuesta", d.get("tiempo_respuesta")),
        ("Dirigido a", d.get("dirigido_a")), ("Teléfono", d.get("telefono")),
        ("Correo", d.get("correo")),
    ]:
        valor = (valor or "No consta en el portal").replace("|", "/")
        partes.append(f"| {etiqueta} | {valor} |")

    for clave, nombre in TITULOS_SECCION.items():
        if s.get(clave):
            partes += ["", f"## {nombre}", "", md(s[clave])]
    otras = [k for k in s if k not in TITULOS_SECCION]
    for k in otras:  # secciones con títulos que no conocemos: se copian igual
        partes += ["", f"## {k.replace('_', ' ').capitalize()}", "", md(s[k])]

    if d.get("oficina") or d.get("horarios"):
        partes += ["", "## Lugares", "", f"### {d.get('oficina') or 'Oficina'}", ""]
        partes += [f"- {h}" for h in d.get("horarios", [])]
    if d.get("formatos"):
        partes += ["", "## Formatos", ""]
        partes += [f"- [{f['nombre']}]({f['url'].replace(' ', '%20')})" for f in d["formatos"]]

    partes += [
        "", "## Fuente", "",
        f"- Ficha: {d.get('url_detalle')}",
        f"- Fecha y hora de extracción: {ahora:%Y-%m-%d %H:%M} (hora de Honduras, UTC-6)",
        FIN,
    ]
    return "\n".join(partes)


def propiedades(r, ahora):
    d = r["datos"]
    titulo = d.get("titulo") or d.get("gestion")
    pregunta = (d.get("categoria") or "").upper().startswith("PREGUNTA")
    dirigido = [x.strip() for x in re.split(r"\s+Y\s+|,", d.get("dirigido_a") or "") if x.strip()]
    lineas = [
        "---",
        f'tipo: "{"pregunta_frecuente" if pregunta else "tramite"}"',
        f"id_portal: {r['codigo']}",
        f"titulo: {q(titulo)}",
        "aliases:",
        f"  - {q(titulo)}",
        f'institucion: "[[10 Trámites del Estado/{INSTITUCION}/{INSTITUCION}|{INSTITUCION}]]"',
        f"gerencia: {q(d.get('gerencia'))}",
        f"unidad: {q(d.get('unidad'))}",
        f"categoria: {q(d.get('categoria'))}",
        f"modalidad: {q((d.get('tipo') or '').capitalize())}",
        "dirigido_a:" if dirigido else "dirigido_a: []",
    ]
    lineas += [f"  - {q(x)}" for x in dirigido]
    lineas += [
        f"costo: {q(d.get('costo'))}",
        f"vigencia: {q(d.get('vigencia'))}",
        f"tiempo_respuesta: {q(d.get('tiempo_respuesta'))}",
        f"oficina: {q(d.get('oficina'))}",
        f"url_ficha: {q(d.get('url_detalle'))}",
        f"extraido: {ahora:%Y-%m-%dT%H:%M}",
        f'huella: "{r["huella_contenido"]}"',
        'estado_portal: "Vigente"',
        "---",
    ]
    return "\n".join(lineas)


def leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)


def notas_existentes(carpeta):
    """id_portal -> ruta, de las notas SPS-*.md que ya están en la bóveda."""
    res = {}
    for sub in ("Trámites", "Preguntas frecuentes"):
        d = os.path.join(carpeta, sub)
        if os.path.isdir(d):
            for n in os.listdir(d):
                m = re.match(r"SPS-(\d+) ", n)
                if m and n.endswith(".md"):
                    res[m.group(1)] = os.path.join(d, n)
    return res


def exportar(registros, carpeta, listado_completo=True, log=print):
    ahora = datetime.now()
    existentes = notas_existentes(carpeta)
    nuevas, cambiadas, iguales = [], [], 0

    for r in registros:
        ruta = ruta_nota(carpeta, r)
        vieja_ruta = existentes.pop(r["codigo"], None)
        anterior = leer(vieja_ruta) if vieja_ruta else None

        if anterior and f'huella: "{r["huella_contenido"]}"' in anterior and 'estado_portal: "Vigente"' in anterior \
                and vieja_ruta == ruta:
            iguales += 1
            continue  # nada cambió: no se toca el archivo (menos trabajo para OneDrive)

        notas_propias = "## Notas propias\n"
        if anterior and FIN in anterior:
            resto = anterior.split(FIN, 1)[1].strip("\n")
            notas_propias = resto + "\n" if resto else notas_propias

        texto = f"{propiedades(r, ahora)}\n{bloque_portal(r, ahora)}\n\n{notas_propias}"
        escribir(ruta, texto)
        if vieja_ruta and vieja_ruta != ruta:
            os.remove(vieja_ruta)  # el título cambió: se renombra conservando Notas propias
        (cambiadas if anterior else nuevas).append(r)

    retiradas = []
    if listado_completo:  # notas cuyo trámite ya no aparece en el portal: se marcan, no se borran
        for codigo, ruta in existentes.items():
            t = leer(ruta)
            if t and 'estado_portal: "Vigente"' in t:
                escribir(ruta, t.replace('estado_portal: "Vigente"', 'estado_portal: "No aparece en el portal"', 1))
                retiradas.append(os.path.basename(ruta))

    escribir_indice(registros, carpeta, ahora)
    if nuevas and not cambiadas and iguales == 0 and not retiradas:  # primera carga: no listar 371 enlaces
        registrar_cambios(carpeta, ahora, [], [], [], f"Carga inicial: {len(nuevas)} notas creadas.")
    else:
        registrar_cambios(carpeta, ahora, nuevas, cambiadas, retiradas)
    log(f"Obsidian: {len(nuevas)} notas nuevas, {len(cambiadas)} actualizadas, "
        f"{iguales} sin cambios, {len(retiradas)} marcadas como retiradas.")
    return nuevas, cambiadas, retiradas


def enlace(carpeta, r):
    return f"[[{os.path.basename(ruta_nota(carpeta, r))[:-3]}|{r['datos'].get('titulo') or r['datos'].get('gestion')}]]"


def escribir_indice(registros, carpeta, ahora):
    tramites = [r for r in registros if not (r["datos"].get("categoria") or "").upper().startswith("PREGUNTA")]
    preguntas = [r for r in registros if r not in tramites]
    partes = [
        "---",
        'tipo: "institucion"',
        f'nombre: "{INSTITUCION}"',
        'portal: "https://www.sanpedrosula.hn/gestion-informativa/"',
        f"actualizado: {ahora:%Y-%m-%dT%H:%M}",
        "---",
        f"# {INSTITUCION}",
        "",
        f"> [!info] Índice generado por el crawler de gestiones de San Pedro Sula. Se reescribe en cada corrida.",
        "",
        f"- Trámites: **{len(tramites)}**",
        f"- Preguntas frecuentes: **{len(preguntas)}**",
        f"- Última extracción: {ahora:%Y-%m-%d %H:%M}",
        "- Historial: [[Registro de cambios SPS]]",
    ]
    for titulo, grupo in (("Trámites", tramites), ("Preguntas frecuentes", preguntas)):
        partes += ["", f"## {titulo}"]
        por_gerencia = {}
        for r in grupo:
            g = r["datos"].get("gerencia") or "Sin gerencia"
            u = r["datos"].get("unidad") or "Sin unidad"
            por_gerencia.setdefault(g, {}).setdefault(u, []).append(r)
        for g in sorted(por_gerencia):
            partes += ["", f"### {g.title()}"]
            for u in sorted(por_gerencia[g]):
                partes += ["", f"**{u.title()}**", ""]
                for r in sorted(por_gerencia[g][u], key=lambda x: int(x["codigo"])):
                    partes.append(f"- {enlace(carpeta, r)}")
    escribir(os.path.join(carpeta, f"{INSTITUCION}.md"), "\n".join(partes) + "\n")


def registrar_cambios(carpeta, ahora, nuevas, cambiadas, retiradas, mensaje=None):
    ruta = os.path.join(carpeta, "Registro de cambios SPS.md")
    anterior = leer(ruta) or "# Registro de cambios SPS\n\nCada corrida del crawler agrega una entrada arriba.\n"
    if mensaje or not (nuevas or cambiadas or retiradas):
        entrada = f"## {ahora:%Y-%m-%d %H:%M}\n\n{mensaje or 'Sin cambios en el portal.'}\n"
    else:
        lineas = [f"## {ahora:%Y-%m-%d %H:%M}", ""]
        if nuevas:
            lineas += [f"**Nuevas ({len(nuevas)})**", ""] + [f"- {enlace(carpeta, r)}" for r in nuevas] + [""]
        if cambiadas:
            lineas += [f"**Actualizadas ({len(cambiadas)})**", ""] + [f"- {enlace(carpeta, r)}" for r in cambiadas] + [""]
        if retiradas:
            lineas += [f"**Ya no aparecen en el portal ({len(retiradas)})**", ""] + [f"- [[{n[:-3]}]]" for n in retiradas] + [""]
        entrada = "\n".join(lineas)
    cabeza, _, cuerpo = anterior.partition("\n## ")
    cuerpo = ("## " + cuerpo) if cuerpo else ""
    escribir(ruta, f"{cabeza.rstrip()}\n\n{entrada}\n{cuerpo}")
