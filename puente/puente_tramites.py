#!/usr/bin/env python3
"""Puente entre el repositorio tramites-estado y la bóveda de Case Deck.

Lo ejecuta la app CaseDeck Motor al final de cada corrida del motor (una línea agregada en
~/Library/Application Support/CaseDeck/ejecutar.sh), así que usa el permiso de Acceso total al disco
que ya tiene esa app. No hace falta darle ese permiso a Python ni a Terminal.

Qué hace:
  1. Baja las novedades del repositorio (git pull, con tiempo límite).
  2. Copia a la bóveda solo las notas de "10 Trámites del Estado" que cambiaron.
     En las notas de trámite y de institución reemplaza las propiedades del portal y el bloque entre
     <!-- portal:inicio --> y <!-- portal:fin -->. Conserva "Notas propias" y cualquier propiedad que agregués.
  3. Genera _Sistema/Equivalencias de instituciones.md para que confirmés la relación con tu catálogo.

Reglas: solo escribe dentro de "10 Trámites del Estado", nunca borra, no toca una nota que editaste hace
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
INICIO = "<!-- portal:inicio -->"
FIN = "<!-- portal:fin -->"
EXTENSIONES = (".md", ".base")

# Propiedades que administra el crawler (mismas listas que crawler/notas.py; una prueba lo verifica)
PROPIEDADES_TRAMITE = [
    "tipo", "id_portal", "titulo", "aliases", "institucion", "responsable", "modalidad", "dirigido_a",
    "costo", "tiempo_respuesta", "comparador_tiempo_dias", "comparador_complejidad", "url_ficha", "url_inicio", "actualizado_portal", "extraido", "huella",
    "estado_portal", "no_aparece_desde",
]
PROPIEDADES_INSTITUCION = ["tipo", "nombre", "siglas_comparador", "id_portal_institucion", "url_listado", "tramites_en_portal"]
GESTIONADAS = set(PROPIEDADES_TRAMITE) | set(PROPIEDADES_INSTITUCION)

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
    for clave, ls in bloques(fm_b):
        if clave not in GESTIONADAS:
            lineas += ls
    return "---\n" + "\n".join(lineas) + "\n---\n" + cuerpo


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


def sincronizar(repo, boveda, estado, gracia_min=10, ahora=None):
    """Copia las notas que cambiaron. Devuelve un resumen."""
    ahora = ahora or time.time()
    origen = os.path.join(repo, CARPETA)
    destino = os.path.join(boveda, CARPETA)
    res = {"nuevas": 0, "actualizadas": 0, "iguales": 0, "en_edicion": 0, "sin_marcadores": [], "rechazadas": []}
    if not os.path.isdir(origen):
        log(f"AVISO no existe {origen}; nada que copiar.")
        return res
    os.makedirs(destino, exist_ok=True)
    for raiz, dirs, archivos in os.walk(origen):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not os.path.islink(os.path.join(raiz, d)))
        for a in sorted(archivos):
            src = os.path.join(raiz, a)
            if a.startswith(".") or not a.endswith(EXTENSIONES) or os.path.islink(src):
                continue
            rel = os.path.relpath(src, origen)
            if any(p in ("..", "") for p in rel.split(os.sep)):
                res["rechazadas"].append(rel)
                continue
            dst = os.path.normpath(os.path.join(destino, rel))
            if not dst.startswith(os.path.normpath(destino) + os.sep):
                res["rechazadas"].append(rel)
                continue
            contenido = leer(src)
            h = sha_texto(contenido)
            clave = CARPETA + "/" + rel.replace(os.sep, "/")
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
    res = sincronizar(repo, boveda, estado.setdefault("aplicadas", {}), int(cfg.get("minutos_de_gracia", 10)))
    hoy = dt.date.today().isoformat()
    if res["nuevas"] or res["actualizadas"] or estado.get("equivalencias") != hoy:
        ruta = os.path.join(boveda, CARPETA, "_Sistema", "Equivalencias de instituciones.md")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        texto = equivalencias(boveda)
        try:
            igual = leer(ruta) == texto
        except OSError:
            igual = False
        if not igual:
            escribir_atomico(ruta, texto)
        estado["equivalencias"] = hoy
    escribir_atomico(ESTADO, json.dumps(estado, ensure_ascii=False, indent=1))
    log(f"Puente: {res['nuevas']} nuevas, {res['actualizadas']} actualizadas, {res['iguales']} sin cambios, "
        f"{res['en_edicion']} en edición (se reintentan en la próxima corrida).")
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
