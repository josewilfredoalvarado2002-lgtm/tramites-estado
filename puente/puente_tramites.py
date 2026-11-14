#!/usr/bin/env python3
"""Puente entre el repositorio tramites-estado y la bóveda de Case Deck.

Lo ejecuta la app CaseDeck Motor al final de cada corrida del motor (una línea agregada en
~/Library/Application Support/CaseDeck/ejecutar.sh), así que usa el permiso de Acceso total al disco
que ya tiene esa app. No hace falta darle ese permiso a Python ni a Terminal.

Qué hace:
  1. Baja las novedades del repositorio (git pull, con tiempo límite).
  2. Copia a la bóveda solo las notas de "10 Trámites del Estado" y "11 Normativa" que cambiaron.
     En las notas de trámite y de institución reemplaza las propiedades del portal y el bloque entre
     <!-- portal:inicio --> y <!-- portal:fin -->. Conserva "Notas propias" y cualquier propiedad que agregués.
  3. Genera _Sistema/Equivalencias de instituciones.md para que confirmés la relación con tu catálogo.

Disposición de la normativa: el repositorio guarda los actos en "11 Normativa/<Tipo>/<Año>" y las ediciones en
"11 Normativa/La Gaceta". En la bóveda quedan ordenados así, y el puente traduce rutas y enlaces al copiar:
  11 Normativa/01 Fuente oficial/La Gaceta/<Año>/...
  11 Normativa/02 Instrumentos normativos/<Año>/<NN Tipo>/<AAAA-MM Mes>/<acto>.md
Además regenera los índices de esa sección (Índice de normativa, Normativa <Año>, <Tipo> <Año> y los meses).
"00 Mapa ejecutivo", "03 Por área" y "99 Sistema" son tuyas: el puente no las toca.

Reglas: solo escribe dentro de "10 Trámites del Estado" y "11 Normativa", nunca borra, no toca una nota que editaste hace
menos de 10 minutos y deja constancia en ~/Library/Application Support/CaseDeck/logs/puente_tramites.log.
Solo usa la biblioteca estándar de Python.
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

SOPORTE = os.path.expanduser("~/Library/Application Support/CaseDeck")
CONFIG = os.path.join(SOPORTE, "puente_tramites.json")
ESTADO = os.path.join(SOPORTE, "puente_tramites_estado.json")
CARPETA = "10 Trámites del Estado"
CARPETAS = [CARPETA, "11 Normativa"]
INICIO = "<!-- portal:inicio -->"
FIN = "<!-- portal:fin -->"
EXTENSIONES = (".md", ".base")

# Disposición de "11 Normativa" en la bóveda
NORMATIVA = "11 Normativa"
FUENTE = "01 Fuente oficial"
INSTRUMENTOS = "02 Instrumentos normativos"
TIPOS_NORMA = {"Acuerdos": "01 Acuerdos", "Decretos": "02 Decretos", "Resoluciones": "03 Resoluciones",
               "Certificaciones": "04 Certificaciones", "Otros actos": "05 Otros actos"}
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
INDICE_NORMATIVA = "Índice de normativa.md"

# Propiedades que administra el crawler (mismas listas que crawler/notas.py; una prueba lo verifica)
PROPIEDADES_TRAMITE = [
    "tipo", "id_portal", "titulo", "aliases", "institucion", "responsable", "modalidad", "dirigido_a",
    "costo", "tiempo_respuesta", "comparador_tiempo_dias", "comparador_complejidad", "url_ficha", "url_inicio", "actualizado_portal", "extraido", "huella",
    "estado_portal", "no_aparece_desde",
]
PROPIEDADES_INSTITUCION = ["tipo", "nombre", "siglas_comparador", "id_portal_institucion", "url_listado", "tramites_en_portal"]
# Propiedades que administra el crawler de La Gaceta (gaceta/texto.py)
PROPIEDADES_NORMA = [
    "tipo", "tipo_acto", "numero", "titulo", "emisor", "gaceta_numero", "gaceta_fecha", "gaceta", "paginas", "sumario",
    "url_pdf", "url_detalle", "extraido", "huella", "paginas_seccion_a", "paginas_seccion_b", "actos",
]
GESTIONADAS = set(PROPIEDADES_TRAMITE) | set(PROPIEDADES_INSTITUCION) | set(PROPIEDADES_NORMA)

CONFIG_POR_DEFECTO = {
    "repositorio": "~/tramites-estado",
    "boveda": "~/Library/CloudStorage/OneDrive-Personal/Case Deck/Case Deck",
    "actualizar_repositorio": True,
    "minutos_de_gracia": 10,
    "segundos_git": 60,
}


def log(msg):
    print(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def sha_texto(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def escribir_atomico(ruta, contenido):
    tmp = os.path.join(os.path.dirname(ruta), f".{os.path.basename(ruta)}.puente.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenido)
    os.replace(tmp, ruta)


# ---------------------------------------------------------------------------
# Fusión de notas
# ---------------------------------------------------------------------------
def separar(texto):
    """Devuelve (lineas_del_frontmatter, cuerpo). Sin frontmatter: ([], texto)."""
    if not texto.startswith("---\n"):
        return [], texto
    fin = texto.find("\n---", 4)
    while fin != -1:
        cierre = texto.find("\n", fin + 1)
        linea = texto[fin + 1: cierre if cierre != -1 else len(texto)]
        if linea.strip() == "---":
            return texto[4:fin].split("\n"), (texto[cierre + 1:] if cierre != -1 else "")
        fin = texto.find("\n---", fin + 1)
    return [], texto


def bloques(lineas_fm):
    """Agrupa el frontmatter por propiedad de primer nivel, conservando el texto original."""
    salida, actual = [], None
    for ln in lineas_fm:
        m = re.match(r"^([^\s#-][^:]*):(\s|$)", ln)
        if m:
            actual = [m.group(1).strip(), [ln]]
            salida.append(actual)
        elif actual is not None:
            actual[1].append(ln)
    return salida


def fusionar(repo, boveda):
    """Nota nueva = propiedades del portal (del repositorio) + propiedades propias (de la bóveda)
    + cuerpo de la bóveda con el bloque del portal reemplazado. Devuelve None si la nota de la
    bóveda perdió los marcadores (no se toca y se avisa)."""
    fm_r, cuerpo_r = separar(repo)
    fm_b, cuerpo_b = separar(boveda)
    i_r, j_r = cuerpo_r.find(INICIO), cuerpo_r.find(FIN)
    i_b, j_b = cuerpo_b.find(INICIO), cuerpo_b.find(FIN)
    if i_r == -1 or j_r == -1 or i_b == -1 or j_b == -1 or j_b < i_b:
        return None
    bloque = cuerpo_r[i_r:j_r + len(FIN)]
    cuerpo = cuerpo_b[:i_b] + bloque + cuerpo_b[j_b + len(FIN):]
    lineas = []
    for _, ls in bloques(fm_r):
        lineas += ls
    claves_repo = {clave for clave, _ in bloques(fm_r)}
    for clave, ls in bloques(fm_b):
        # se conservan las propiedades propias de la bóveda; las que trae el repositorio las reemplazan
        if clave not in GESTIONADAS and clave not in claves_repo:
            lineas += ls
    return "---\n" + "\n".join(lineas) + "\n---\n" + cuerpo


# ---------------------------------------------------------------------------
# Disposición de la normativa en la bóveda
# ---------------------------------------------------------------------------
def _nfc(s):
    return unicodedata.normalize("NFC", s)


def destino_normativa(rel, contenido):
    """Ruta dentro de "11 Normativa" de la bóveda para una nota del repositorio (rel con "/").
    Devuelve None para las notas que el puente genera por su cuenta (el índice general)."""
    rel = _nfc(rel)
    partes = rel.split("/")
    if rel == INDICE_NORMATIVA:
        return None
    if partes[0] == "La Gaceta":
        return FUENTE + "/" + rel
    if partes[0] in TIPOS_NORMA and len(partes) == 3:
        m = re.search(r'^gaceta_fecha:\s*"?(\d{4})-(\d{2})', contenido, re.M)
        if m and 1 <= int(m.group(2)) <= 12:
            anio, mes = m.group(1), f"{m.group(1)}-{m.group(2)} {MESES[int(m.group(2))]}"
        else:
            anio, mes = partes[1], "Sin fecha"
        return f"{INSTRUMENTOS}/{anio}/{TIPOS_NORMA[partes[0]]}/{mes}/{partes[2]}"
    return rel


_ENLACE_NORMATIVA = re.compile(
    r"11 Normativa/((?:La Gaceta|" + "|".join(TIPOS_NORMA) + r")/[^\]\[|\\#\n]+)")


def mapa_normativa(origen):
    """Para cada nota del repositorio: ruta sin extensión -> ruta sin extensión en la bóveda."""
    mapa = {}
    for raiz, dirs, archivos in os.walk(origen):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for a in archivos:
            if not a.endswith(".md") or a.startswith("."):
                continue
            rel = _nfc(os.path.relpath(os.path.join(raiz, a), origen).replace(os.sep, "/"))
            if rel.split("/")[0] in TIPOS_NORMA:
                try:
                    with open(os.path.join(raiz, a), encoding="utf-8") as f:
                        cabeza = f.read(2500)
                except OSError:
                    continue
            else:
                cabeza = ""
            d = destino_normativa(rel, cabeza)
            if d:
                mapa[rel[:-3]] = d[:-3]
    return mapa


def reescribir_enlaces(contenido, mapa):
    """Cambia los enlaces con la ruta del repositorio por la ruta de la bóveda."""
    def cambio(m):
        viejo = _nfc(m.group(1)).rstrip()
        nuevo = mapa.get(viejo)
        if nuevo is None and viejo.startswith("La Gaceta/"):
            nuevo = FUENTE + "/" + viejo
        return "11 Normativa/" + (nuevo if nuevo else m.group(1))
    return _ENLACE_NORMATIVA.sub(cambio, contenido)


def _escribir_si_cambia(ruta, texto):
    try:
        if leer(ruta) == texto:
            return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    escribir_atomico(ruta, texto)
    return True


def _titulo_de(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            m = re.search(r'^titulo:\s*"?(.*?)"?\s*$', f.read(2500), re.M)
    except OSError:
        m = None
    t = (m.group(1) if m else "") or os.path.basename(ruta)[:-3]
    return t.replace("|", "/").replace("[", "(").replace("]", ")")


def indices_normativa(boveda):
    """Regenera los índices de 11 Normativa a partir de lo que hay en la bóveda. Devuelve cuántos cambió."""
    base = os.path.join(boveda, NORMATIVA)
    inst = os.path.join(base, INSTRUMENTOS)
    cab = '---\ntipo: "normativa_indice"\n---\n\n'
    cambios, anios = 0, []
    if os.path.isdir(inst):
        anios = sorted(_nfc(d) for d in os.listdir(inst) if d.isdigit() and os.path.isdir(os.path.join(inst, d)))
    for anio in anios:
        tipos = []
        for carpeta_tipo in sorted(_nfc(d) for d in os.listdir(os.path.join(inst, anio))):
            dir_tipo = os.path.join(inst, anio, carpeta_tipo)
            if not os.path.isdir(dir_tipo) or carpeta_tipo.startswith("."):
                continue
            nombre = carpeta_tipo[3:] if re.match(r"\d\d ", carpeta_tipo) else carpeta_tipo
            ruta_tipo = f"{NORMATIVA}/{INSTRUMENTOS}/{anio}/{carpeta_tipo}"
            meses = []
            for mes in sorted(_nfc(d) for d in os.listdir(dir_tipo)):
                dir_mes = os.path.join(dir_tipo, mes)
                if not os.path.isdir(dir_mes) or mes.startswith("."):
                    continue
                notas = sorted(_nfc(a) for a in os.listdir(dir_mes) if a.endswith(".md") and not a.startswith("."))
                if not notas:
                    continue
                meses.append(mes)
                n = len(notas)
                L = [f"# {nombre} · {mes}", "",
                     f"{n} instrumento{'s' if n != 1 else ''} publicado{'s' if n != 1 else ''} durante este mes.", "",
                     "## Documentos"]
                L += [f"- [[{ruta_tipo}/{mes}/{a[:-3]}|{_titulo_de(os.path.join(dir_mes, a))}]]" for a in notas]
                cambios += _escribir_si_cambia(os.path.join(dir_tipo, mes + ".md"), cab + "\n".join(L) + "\n")
            if not meses:
                continue
            tipos.append((carpeta_tipo, nombre))
            L = [f"# {nombre} {anio}", "", f"Índice cronológico de {nombre.lower()} publicados durante {anio}.", "", "## Meses"]
            L += [f"- [[{ruta_tipo}/{m}|{m}]]" for m in meses]
            cambios += _escribir_si_cambia(os.path.join(dir_tipo, f"{nombre} {anio}.md"), cab + "\n".join(L) + "\n")
        L = [f"# Normativa {anio}", "", f"Puerta de entrada a los instrumentos normativos publicados durante {anio}.", "",
             "## Fuente oficial", f"- [[{NORMATIVA}/{FUENTE}/La Gaceta/La Gaceta {anio}|La Gaceta {anio}]]", "",
             "## Por tipo de instrumento"]
        L += [f"- [[{NORMATIVA}/{INSTRUMENTOS}/{anio}/{c}/{n} {anio}|{n} {anio}]]" for c, n in tipos]
        cambios += _escribir_si_cambia(os.path.join(inst, anio, f"Normativa {anio}.md"), cab + "\n".join(L) + "\n")
    gacetas = os.path.join(base, FUENTE, "La Gaceta")
    fuentes = []
    if os.path.isdir(gacetas):
        fuentes = sorted(_nfc(a)[:-3] for a in os.listdir(gacetas) if re.match(r"La Gaceta \d{4}\.md$", _nfc(a)))
    L = ["# Índice de normativa", "", "Biblioteca normativa organizada por año, tipo de instrumento y mes de publicación.", ""]
    if os.path.exists(os.path.join(base, "00 Mapa ejecutivo", "Mapa jurídico.md")):
        L += ["## Explorar por área", f"- [[{NORMATIVA}/00 Mapa ejecutivo/Mapa jurídico|Mapa jurídico]]", ""]
    L += ["## Explorar por año"] + [f"- [[{NORMATIVA}/{INSTRUMENTOS}/{a}/Normativa {a}]]" for a in anios]
    L += ["", "## Fuente oficial"] + [f"- [[{NORMATIVA}/{FUENTE}/La Gaceta/{f}]]" for f in fuentes]
    L += ["", "## Conexión con el resto de la bóveda",
          f"[[{CARPETA}/Índice de trámites|Índice de trámites]]. Es el único enlace de la normativa hacia fuera, para que en la "
          "vista de grafo se vean tres redes en cadena: Normativa, Trámites y Directorio."]
    cambios += _escribir_si_cambia(os.path.join(base, INDICE_NORMATIVA), cab + "\n".join(L) + "\n")
    return cambios


# ---------------------------------------------------------------------------
# Equivalencias con 09 Catálogos/Instituciones (solo lectura de esa carpeta)
# ---------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.casefold().split())


def _propiedad(fm_lineas, clave):
    for c, ls in bloques(fm_lineas):
        if c == clave:
            v = ls[0].split(":", 1)[1].strip()
            if v:
                return [v.strip('"')]
            return [x.strip()[1:].strip().strip('"') for x in ls[1:] if x.strip().startswith("-")]
    return []


def equivalencias(boveda):
    destino = os.path.join(boveda, CARPETA)
    catalogo = os.path.join(boveda, "09 Catálogos", "Instituciones")
    candidatos = {}
    if os.path.isdir(catalogo):
        for a in sorted(os.listdir(catalogo)):
            if not a.endswith(".md") or a.startswith("."):
                continue
            nombre = a[:-3]
            try:
                fm, _ = separar(leer(os.path.join(catalogo, a)))
            except OSError:
                continue
            for n in [nombre] + _propiedad(fm, "aliases") + _propiedad(fm, "nombre") + _propiedad(fm, "siglas"):
                if n:
                    candidatos.setdefault(_norm(n), set()).add(nombre)
    filas = []
    for raiz, dirs, archivos in os.walk(destino):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "_Sistema"]
        for a in archivos:
            if not a.endswith(".md"):
                continue
            try:
                fm, _ = separar(leer(os.path.join(raiz, a)))
            except OSError:
                continue
            if _propiedad(fm, "tipo") != ["institucion_portal"]:
                continue
            nombre = (_propiedad(fm, "nombre") or [a[:-3]])[0]
            siglas = (_propiedad(fm, "siglas_comparador") or [""])[0]
            conf = (_propiedad(fm, "catalogo_case_deck") or [""])[0]
            cand = sorted(candidatos.get(_norm(nombre), set()) | (candidatos.get(_norm(siglas), set()) if siglas else set()))
            ruta = os.path.relpath(os.path.join(raiz, a[:-3]), boveda).replace(os.sep, "/")
            filas.append((nombre, ruta, a[:-3], cand, conf))
    L = ["---", "tipo: sistema", "---", "", "# Equivalencias de instituciones", "",
         "Relación entre las instituciones del portal y tus notas de `09 Catálogos/Instituciones`. "
         "La columna de candidatas solo muestra notas cuyo nombre, alias o siglas coinciden exactamente (sin tildes ni mayúsculas). "
         "Nada se da por equivalente: para confirmar una, abrí la nota de la institución del portal y escribí en la propiedad "
         "`catalogo_case_deck` el enlace a la nota de tu catálogo. El puente regenera esta tabla y nunca escribe en 09 Catálogos.", "",
         "Cuando una nota de tu catálogo se llama igual que la del portal, Obsidian tiene dos notas con el mismo nombre y un enlace "
         "sin ruta puede abrir la que no es. Esos casos aparecen marcados con «mismo nombre».", "",
         f"Notas en 09 Catálogos/Instituciones: {len({n for s in candidatos.values() for n in s})}.", "",
         "| Institución en el portal | Nota del portal | Candidata en tu catálogo (por confirmar) | Confirmada en la nota |",
         "| --- | --- | --- | --- |"]
    for nombre, ruta, nota, cand, conf in sorted(filas, key=lambda x: _norm(x[0])):
        c = ", ".join(f"[[09 Catálogos/Instituciones/{x}\\|{x}]]" + (" (mismo nombre)" if x == nota else "") for x in cand) or "Sin candidata"
        L.append(f"| {nombre.replace('|', '/')} | [[{ruta}\\|{nota}]] | {c} | {conf.replace('|', '/') or 'Pendiente'} |")
    if not filas:
        L.append("| Sin instituciones todavía | | | |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------
def cargar_config():
    cfg = dict(CONFIG_POR_DEFECTO)
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg["repositorio"] = os.path.expanduser(cfg["repositorio"])
    cfg["boveda"] = os.path.expanduser(cfg["boveda"])
    return cfg


def actualizar_repo(repo, segundos):
    try:
        r = subprocess.run(["git", "-C", repo, "pull", "--ff-only", "--quiet"], capture_output=True, text=True,
                           timeout=segundos, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode != 0:
            log(f"AVISO git pull terminó con código {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}. Se usa la copia local.")
    except subprocess.TimeoutExpired:
        log(f"AVISO git pull tardó más de {segundos} s. Se usa la copia local.")
    except FileNotFoundError:
        log("AVISO no se encontró git. Se usa la copia local.")


def dentro_de(base, ruta):
    base = os.path.realpath(base)
    ruta = os.path.realpath(ruta)
    return ruta == base or ruta.startswith(base + os.sep)


def sincronizar(repo, boveda, estado, gracia_min=10, ahora=None, carpeta=CARPETA):
    """Copia las notas que cambiaron. Devuelve un resumen."""
    ahora = ahora or time.time()
    origen = os.path.join(repo, carpeta)
    destino = os.path.join(boveda, carpeta)
    res = {"nuevas": 0, "actualizadas": 0, "iguales": 0, "en_edicion": 0, "sin_marcadores": [], "rechazadas": [],
           "pendientes": []}
    if not os.path.isdir(origen):
        log(f"AVISO no existe {origen}; nada que copiar.")
        return res
    os.makedirs(destino, exist_ok=True)
    normativa = _nfc(carpeta) == NORMATIVA
    mapa = mapa_normativa(origen) if normativa else {}
    for raiz, dirs, archivos in os.walk(origen):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not os.path.islink(os.path.join(raiz, d)))
        for a in sorted(archivos):
            try:
                src = os.path.join(raiz, a)
                if a.startswith(".") or not a.endswith(EXTENSIONES) or os.path.islink(src):
                    continue
                rel = os.path.relpath(src, origen)
                if any(p in ("..", "") for p in rel.split(os.sep)):
                    res["rechazadas"].append(rel)
                    continue
                contenido = leer(src)
                h = sha_texto(contenido)
                rel_destino = rel
                if normativa:
                    # la huella es la del repositorio; la ruta y los enlaces se traducen a la disposición de la bóveda
                    rel_destino = destino_normativa(rel.replace(os.sep, "/"), contenido)
                    if rel_destino is None:
                        continue
                    rel_destino = rel_destino.replace("/", os.sep)
                    contenido = reescribir_enlaces(contenido, mapa)
                dst = os.path.normpath(os.path.join(destino, rel_destino))
                if not dst.startswith(os.path.normpath(destino) + os.sep):
                    res["rechazadas"].append(rel)
                    continue
                clave = carpeta + "/" + rel.replace(os.sep, "/")
                existe = os.path.exists(dst)
                previo = estado.get(clave) or {}
                if previo.get("huella") == h and existe:
                    res["iguales"] += 1
                    continue
                # antes de crear carpetas se comprueba que la parte que ya existe no salga de la carpeta 10
                existente = os.path.dirname(dst)
                while not os.path.exists(existente):
                    existente = os.path.dirname(existente)
                if not dentro_de(destino, existente) or os.path.islink(dst):
                    res["rechazadas"].append(rel)
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not existe:
                    escribir_atomico(dst, contenido)
                    estado[clave] = {"huella": h, "mtime": os.path.getmtime(dst)}
                    res["nuevas"] += 1
                    continue
                mtime = os.path.getmtime(dst)
                # una nota que vos modificaste hace poco se deja para la siguiente corrida;
                # lo que escribió el propio puente no cuenta como edición
                if mtime != previo.get("mtime") and ahora - mtime < gracia_min * 60:
                    res["en_edicion"] += 1
                    continue
                actual = leer(dst)
                if INICIO in contenido:
                    nuevo = fusionar(contenido, actual)
                    if nuevo is None:
                        res["sin_marcadores"].append(clave)
                        continue
                else:
                    nuevo = contenido
                if nuevo != actual:
                    escribir_atomico(dst, nuevo)
                    res["actualizadas"] += 1
                else:
                    res["iguales"] += 1
                estado[clave] = {"huella": h, "mtime": os.path.getmtime(dst)}
            except OSError as e:
                # típico de OneDrive con archivos solo en la nube (TimeoutError): se reintenta la próxima vez
                res["pendientes"].append(f"{carpeta}/{a}: {type(e).__name__}")
    return res


def main():
    cfg = cargar_config()
    repo, boveda = cfg["repositorio"], cfg["boveda"]
    if not os.path.isdir(os.path.join(boveda, ".casedeck")):
        log(f"ERROR no encuentro la bóveda de Case Deck en {boveda}. Revisá {CONFIG}.")
        return 1
    if dentro_de(boveda, repo) or os.path.exists(os.path.join(boveda, ".git")):
        log("ERROR el repositorio no puede estar dentro de la bóveda (ni puede haber una carpeta .git en ella).")
        return 1
    if not os.path.isdir(os.path.join(repo, ".git")):
        log(f"ERROR no encuentro el repositorio en {repo}. Revisá {CONFIG}.")
        return 1
    if cfg.get("actualizar_repositorio", True):
        actualizar_repo(repo, int(cfg.get("segundos_git", 60)))
    try:
        with open(ESTADO, encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = {}
    res = None
    for carpeta in CARPETAS:
        r = sincronizar(repo, boveda, estado.setdefault("aplicadas", {}), int(cfg.get("minutos_de_gracia", 10)), carpeta=carpeta)
        if _nfc(carpeta) == NORMATIVA and os.path.isdir(os.path.join(boveda, NORMATIVA)):
            falta = not os.path.exists(os.path.join(boveda, NORMATIVA, INDICE_NORMATIVA))
            if r["nuevas"] or falta:
                log(f"Normativa: {indices_normativa(boveda)} índices regenerados.")
        if res is None:
            res = r
        else:
            for k, v in r.items():
                res[k] += v
    hoy = dt.date.today().isoformat()
    if res["nuevas"] or res["actualizadas"] or estado.get("equivalencias") != hoy:
        ruta = os.path.join(boveda, CARPETA, "_Sistema", "Equivalencias de instituciones.md")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        try:
            texto = equivalencias(boveda)
            try:
                igual = leer(ruta) == texto
            except OSError:
                igual = False
            if not igual:
                escribir_atomico(ruta, texto)
            estado["equivalencias"] = hoy
        except OSError as e:
            log(f"AVISO no se regeneró Equivalencias de instituciones ({type(e).__name__}); se reintenta la próxima vez.")
    escribir_atomico(ESTADO, json.dumps(estado, ensure_ascii=False, indent=1))
    log(f"Puente: {res['nuevas']} nuevas, {res['actualizadas']} actualizadas, {res['iguales']} sin cambios, "
        f"{res['en_edicion']} en edición (se reintentan en la próxima corrida).")
    if res.get("pendientes"):
        log(f"AVISO {len(res['pendientes'])} notas no se pudieron leer a tiempo (OneDrive las tiene solo en la nube); "
            f"se reintentan en la próxima corrida. Primera: {res['pendientes'][0]}")
    for c in res["sin_marcadores"]:
        log(f"AVISO {c}: la nota de la bóveda perdió los marcadores portal:inicio/portal:fin; no se tocó.")
    for c in res["rechazadas"]:
        log(f"AVISO ruta rechazada por seguridad: {c}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        log(f"ERROR inesperado en el puente: {type(e).__name__}: {e}")
        sys.exit(1)
