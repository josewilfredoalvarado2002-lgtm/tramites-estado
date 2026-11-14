"""Reparación del armado del texto que sale de los PDF (capa 1 del corrector).

Solo corrige errores de extracción con reglas fijas; no cambia palabras ni redacción del texto oficial:
  1. Sumario pegado del portal de la ENAG: «FINANZASAcuerdo No. 5» -> «FINANZAS: Acuerdo No. 5».
  2. Números cortados: «Decreto No. 170- 2016» -> «170-2016»; «PCM- 02-2007» -> «PCM-02-2007».
  3. Párrafos partidos a media frase: un párrafo que termina en «No.» seguido de uno que empieza con el
     número, o uno sin punto final seguido de otro que empieza en minúscula, se unen.
  4. Palabras partidas con guion («sub- sector», «técnica- administrativa»): solo se unen si la forma
     unida («subsector») o con guion («técnica-administrativa») ya aparece escrita en la colección.
     Si no aparece, se deja como está: puede ser una raya («petróleo- ya»).
  5. Títulos con letras separadas («D E L A R E P Ú B L I C A»): se juntan y se vuelven a partir en
     palabras que ya aparecen en la colección («DE LA REPÚBLICA»). Si algún pedazo no es una palabra
     conocida, se deja como está.
  6. Espacios: dobles espacios, espacio antes de coma o punto y coma, y «No.83» -> «No. 83».

Uso para las notas ya cargadas:  python3 -m gaceta.reparar [carpeta_del_repositorio]
"""
import hashlib
import math
import os
import re
import sys
from collections import Counter

MAY = "A-ZÁÉÍÓÚÑÜ"
MIN = "a-záéíóúñü"
_PEGADO = re.compile(rf"([{MAY}]{{3}})(?=[{MAY}][{MIN}]{{2,}})")
_NUM_MAY = re.compile(rf"(\d)(?=[{MAY}]{{4,}}\b)")
_NUM = re.compile(r"(\b(?:\d+|[A-Z]{2,}))- (?=\d)")
_GUION = re.compile(rf"\b([{MIN}]{{2,}})- ([{MIN}]{{2,}})\b")
_ABREV = re.compile(r"\b(?:No|Nos|N°|Nº|Núm|Número|Números)\.?$")
_SEPARADAS = re.compile(rf"(?<![\w])((?:[{MAY}{MIN}] ){{3,}}[{MAY}{MIN}])(?![\w])")
_SUELTAS = {"y", "a", "o", "e", "u"}
_CORTAS = _SUELTAS | {"de", "la", "el", "en", "del", "los", "las", "al", "se", "no", "su", "sus", "un", "una", "por",
                      "con", "que", "lo", "le", "es", "ni", "mi", "sin", "sea", "son", "fue", "ser", "dos", "tres"}
_PALABRA = re.compile(rf"[{MAY}{MIN}]+(?:-[{MAY}{MIN}]+)?")


def sumario(s):
    """Separa el emisor del acto en las líneas del sumario del portal."""
    s = _PEGADO.sub(r"\1: ", s)
    return _NUM_MAY.sub(r"\1; ", s)


def vocabulario(textos):
    c = Counter()
    for t in textos:
        c.update(w.lower() for w in _PALABRA.findall(t))
    return {w: n for w, n in c.items() if n >= 2}


def _partir(letras, voc, total):
    """Divide «DELAREPÚBLICA» en palabras conocidas con la combinación más probable."""
    low, n = letras.lower(), len(letras)
    mejor = [(0.0, -1)] + [(math.inf, -1)] * n
    for j in range(1, n + 1):
        for i in range(max(0, j - 25), j):
            w = low[i:j]
            if mejor[i][0] == math.inf or (len(w) == 1 and w not in _SUELTAS) or w not in voc:
                continue
            c = mejor[i][0] + math.log(total / voc[w]) + 3.0   # 3.0: castigo por palabra extra
            if c < mejor[j][0]:
                mejor[j] = (c, i)
    if mejor[n][0] == math.inf:
        return None
    cortes, j = [], n
    while j > 0:
        i = mejor[j][1]
        cortes.append(letras[i:j])
        j = i
    # Un pedazo corto que no es palabra común ni número romano delata un corte inventado («ces os»).
    if any(len(w) <= 3 and w.lower() not in _CORTAS and not re.fullmatch(r"[IVXLC]+", w) for w in cortes):
        return None
    return " ".join(reversed(cortes))


def _separadas(p, voc):
    if not isinstance(voc, dict) or not voc:
        return p
    total = sum(voc.values())
    return _SEPARADAS.sub(lambda m: _partir(m.group(1).replace(" ", ""), voc, total) or m.group(0), p)


_PREFIJOS = {"sub", "semi", "contra", "anti", "pre", "pos", "post", "re", "co", "inter", "intra", "extra", "micro",
             "macro", "multi", "super", "termo", "auto", "bio", "eco", "geo", "hidro", "electro", "infra", "ultra",
             "mini", "vice", "sobre", "seudo", "pluri", "bi", "tri"}


def _guiones(p, voc):
    def rep(m):
        a, b = m.group(1), m.group(2)
        unida, compuesta = (a + b).lower(), f"{a}-{b}".lower()
        if unida in voc and (b.lower() not in voc or a.lower() in _PREFIJOS):
            return a + b                      # palabra partida: «carne- tizada», «sub- sector»
        if compuesta in voc:
            return f"{a}-{b}"                 # compuesta: «técnica- administrativa»
        return m.group(0)                     # puede ser una raya: «petróleo- ya»
    return _GUION.sub(rep, p)


def linea(p, voc=frozenset()):
    p = _NUM.sub(r"\1-", p)
    p = _guiones(p, voc)
    p = _separadas(p, voc)
    p = re.sub(r"\b(No|Nos|N°)\.(?=\d)", r"\1. ", p)
    p = re.sub(r"(?<=\S)  +", " ", p)
    p = re.sub(rf"(?<=[{MAY}{MIN}0-9)]) +(?=[,;])", "", p)
    return re.sub(rf"(?<=[{MAY}{MIN}]) +(?=:)", "", p)


def _es_bloque(p):
    return p.startswith(("#", "|", ">", "- ", "\\", "<!--")) or not p.strip()


def _unir(a, b):
    if _es_bloque(a) or _es_bloque(b):
        return False
    if _ABREV.search(a) and re.match(r"(?:\d|[A-Z]{2,}-)", b):
        return True
    if re.match(r"[a-zñ][.)]\s|[ivx]{1,4}[.)]\s", b):  # incisos «a)», «ii.»
        return False
    return a[-1] not in ".:;!?)\"”" and b[0].islower()


def texto(md, voc=frozenset()):
    """md: el texto de un acto, en párrafos separados por línea en blanco."""
    out = []
    for p in md.split("\n\n"):
        if out and _unir(out[-1], p):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return "\n\n".join(p if _es_bloque(p) else linea(p, voc) for p in out)


# ---------- texto de documentos de los trámites (renglón por renglón) ----------

_CORTE_FIN = re.compile(rf"\b(?:y|e|o|u|de|del|la|las|el|los|en|a|al|con|por|para|que|su|sus|un|una|se|sin|como)$", re.I)
_ITEM = re.compile(r"^(?:[-•●▪■–*]\s|\d{1,3}[.)-]\s|[a-zñ][.)]\s|[IVXL]{1,5}[.)]\s|\(\w{1,3}\)\s|\\)")
_GUION_FIN = re.compile(rf"([{MAY}{MIN}]{{2,}})-$")


def documento(md, voc=frozenset()):
    """Rearma los párrafos de un texto de PDF que viene renglón por renglón: une el renglón que sigue
    a media frase (empieza en minúscula, o el anterior termina en coma o en «y», «de», «la»...) y
    las palabras partidas con guion al final del renglón. No une viñetas, numerales ni títulos."""
    out = []
    for x in md.split("\n"):
        if out and out[-1].strip() and x.strip() and not _ITEM.match(x) and not _es_bloque(x) \
                and not _es_bloque(out[-1]):
            a = out[-1].rstrip()
            m = _GUION_FIN.search(a)
            if m and x[0].isalpha():
                b = re.match(rf"[{MAY}{MIN}]+", x).group(0)
                if (m.group(1) + b).lower() in voc:
                    out[-1] = a[:-1] + x
                    continue
            elif a[-1] not in ".:;!?" and (x[0].islower() or a[-1] == "," or _CORTE_FIN.search(a)):
                out[-1] = a + " " + x
                continue
        out.append(x)
    return "\n".join(linea(x, voc) if x.strip() and not _es_bloque(x) else x for x in out)


def es_seccion_documento(titulo):
    return "según el documento" in titulo or "Otro texto del documento" in titulo


def reparar_tramite(nota, voc):
    partes = re.split(r"(?m)^(## .*)$", nota)
    for i in range(1, len(partes) - 1, 2):
        if es_seccion_documento(partes[i]):
            cuerpo = partes[i + 1]
            fin = cuerpo.find("<!-- portal:fin -->")
            pedazo, resto = (cuerpo[:fin], cuerpo[fin:]) if fin >= 0 else (cuerpo, "")
            partes[i + 1] = documento(pedazo, voc) + resto
    return "".join(partes)


def reparar_tramites(repo, voc=None):
    voc = voc if voc is not None else vocabulario_repo(repo)
    cambiadas = 0
    for raiz, _, archivos in os.walk(os.path.join(repo, "10 Trámites del Estado")):
        for a in archivos:
            if not a.endswith(".md"):
                continue
            ruta = os.path.join(raiz, a)
            with open(ruta, encoding="utf-8") as f:
                t = f.read()
            partes = t.split("<!-- portal:fin -->", 1)
            if len(partes) != 2 or "según el documento" not in partes[0]:
                continue
            nuevo = reparar_tramite(partes[0], voc) + "<!-- portal:fin -->" + partes[1]
            if nuevo != t:
                with open(ruta, "w", encoding="utf-8", newline="\n") as f:
                    f.write(nuevo)
                cambiadas += 1
    print(f"Reparación del texto: {cambiadas} trámites con texto de documentos corregidos.")
    return cambiadas


# ---------- notas ya cargadas ----------

def _seccion(nota, ini, fin):
    a = nota.find(ini)
    if a < 0:
        return None
    a += len(ini)
    b = nota.find(fin, a)
    return (a, b) if b >= 0 else None


def reparar_nota(nota, voc):
    """Repara una nota de acto o de edición de La Gaceta. Devuelve el texto nuevo."""
    edicion = re.search(r'^tipo: "?gaceta"?$', nota, re.M) is not None
    lineas = nota.split("\n")
    for i, x in enumerate(lineas):
        if re.match(r'^(titulo|sumario): "', x) or x.startswith("# ") or x.startswith("| Según el sumario") \
                or (edicion and x.startswith("- ") and not x.startswith("- [[")):
            lineas[i] = sumario(x)
    nota = "\n".join(lineas)
    r = _seccion(nota, "\n## Texto\n\n", "\n\n## Fuente")
    if r:
        cuerpo = texto(nota[r[0]:r[1]], voc)
        nota = nota[:r[0]] + cuerpo + nota[r[1]:]
        huella = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()[:16]
        nota = re.sub(r'^huella: ".*"$', f'huella: "{huella}"', nota, count=1, flags=re.M)
    return nota


def _notas(repo):
    for raiz, _, archivos in os.walk(os.path.join(repo, "11 Normativa")):
        for a in archivos:
            if a.endswith(".md"):
                yield os.path.join(raiz, a)


def vocabulario_repo(repo):
    textos = []
    for ruta in _notas(repo):
        with open(ruta, encoding="utf-8") as f:
            t = f.read()
        r = _seccion(t, "\n## Texto\n\n", "\n\n## Fuente")
        if r:
            textos.append(t[r[0]:r[1]])
    return vocabulario(textos)


def reparar_repo(repo):
    voc = vocabulario_repo(repo)
    cambiadas = 0
    for ruta in _notas(repo):
        with open(ruta, encoding="utf-8") as f:
            t = f.read()
        if "<!-- portal:inicio -->" not in t:
            continue
        partes = t.split("<!-- portal:fin -->", 1)   # «Notas propias» queda intacto
        nuevo = reparar_nota(partes[0], voc) + "<!-- portal:fin -->" + partes[1] if len(partes) == 2 else t
        if nuevo != t:
            with open(ruta, "w", encoding="utf-8", newline="\n") as f:
                f.write(nuevo)
            cambiadas += 1
    print(f"Reparación del texto: {cambiadas} notas de La Gaceta corregidas.")
    return cambiadas


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reparar_repo(repo)
    reparar_tramites(repo)
