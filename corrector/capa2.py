"""Capa 2 del corrector: revisión de ortografía y gramática de las fichas de trámites con LanguageTool.

No cambia ninguna nota. Lee el bloque del portal de cada ficha, le pasa a LanguageTool solo la prosa
(sin tablas, enlaces, correos, códigos ni números) y guarda los posibles errores en
revision/hallazgos.json. En la bóveda, el puente convierte ese archivo en la nota «Revisión de textos»,
donde vos marcás qué se corrige y qué se deja; solo lo que marcás se aplica.

Solo se proponen tildes (poner o quitar una tilde: «vehiculo» -> «vehículo», «dictámen» -> «dictamen»).
Nunca se agregan, quitan ni cambian palabras o letras: el texto sigue siendo el de la fuente oficial.

Para que la lista sea corta y útil, además se descartan:
  - las reglas de estilo, tipografía y mayúsculas (no son errores de ortografía);
  - las palabras con mayúscula inicial o en mayúsculas (casi siempre son nombres propios o siglas);
  - las palabras que se repiten escritas igual en 3 fichas o más (términos técnicos, nombres de sistemas);
  - los avisos sin una corrección concreta que proponer.

Uso:  python3 -m corrector.capa2 [carpeta_del_repositorio]
      (necesita Java y el paquete language_tool_python; en GitHub corre en el flujo sitios.yml)
"""
import hashlib
import unicodedata
import json
import os
import re
import sys
from collections import Counter

INICIO, FIN = "<!-- portal:inicio -->", "<!-- portal:fin -->"
CARPETA = "10 Trámites del Estado"
SALIDA = os.path.join("revision", "hallazgos.json")

MAY = "A-ZÁÉÍÓÚÑÜ"
MIN = "a-záéíóúñü"
_PALABRA = re.compile(rf"[{MAY}{MIN}]+")

# Partes de la línea que no son prosa: se tapan con espacios para que LanguageTool no las lea,
# sin mover las posiciones del resto del texto.
_TAPAR = [
    re.compile(r"\[\[[^\]]*\]\]"),                 # enlaces internos
    re.compile(r"\]\([^)]*\)"),                    # destino de enlaces markdown
    re.compile(r"https?://\S+|www\.\S+"),          # direcciones web
    re.compile(r"\S+@\S+|\[email protected\]"),   # correos (y los que el portal ocultó)
    re.compile(r"\\[#*_\[\]()|-]"),                # escapes de markdown
    re.compile(r"\S*\d\S*"),                       # números, códigos, fechas, montos
    re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s+\d+[.)])?\s+"),  # viñetas y numerales
    re.compile(r"[*_`]+"),                         # negritas, cursivas, código
]
# Líneas que no se revisan
_SALTAR = re.compile(r"^\s*(?:\||#|>|<!--|- Documento|- Documento enlazado|\s*- Dependencia: *$)")

# Solo estas categorías de LanguageTool llegan a la lista
CATEGORIAS = {"TYPOS", "GRAMMAR", "CONFUSED_WORDS", "MISC", "DIACRITICS", "SEMANTICS"}
# Reglas que dan más ruido que ayuda en textos administrativos copiados de portales
REGLAS_FUERA = {
    "WHITESPACE_RULE", "UPPERCASE_SENTENCE_START", "COMMA_PARENTHESIS_WHITESPACE", "DOUBLE_PUNCTUATION",
    "ES_UNPAIRED_BRACKETS", "UNPAIRED_BRACKETS", "PUNCTUATION_PARAGRAPH_END", "ES_QUESTION_MARK",
    "EN_QUOTES", "TYPOGRAPHY", "ES_WIKIPEDIA_COMMON_ERRORS", "SPACE_AFTER_PUNCTUATION",
    "TOO_LONG_SENTENCE", "ES_REPEATEDWORDS", "PHRASE_REPETITION", "ES_SPLIT_WORDS",
    # sugerencias de estilo o que dependen de la intención del autor
    "EN_BASE_A", "EN_BASE_AL", "SI_AFIRMACION", "ES_SIMPLE_REPLACE_SIMPLE_EN_BASE",
    # en la prueba con todas las fichas se equivocaron más de lo que acertaron
    # («soporte» -> «soporté», «el (los) bote(s)» -> «él», «PAN PAN» repetido a propósito)
    "EL_TILDE", "SUBJUNTIVO_PASADO", "SUBJUNTIVO_INCORRECTO", "PREP_VERB", "SPANISH_WORD_REPEAT_RULE",
}
# Un renglón donde LanguageTool no reconoce ni la tercera parte de las palabras no es español legible:
# es otro idioma o texto del PDF que salió revuelto. Ahí no se propone nada.
MAX_DESCONOCIDAS = 0.34
_EN = set("the of and is are to in with was be or on at from by for has have not this that it as an will".split())
_ES = set("de la el que y en los del las por con para se una un su al es lo como".split())
_SOLO_LETRAS = re.compile(rf"^[{MAY}{MIN}]+$")


def diccionario_ingles(ruta="/usr/share/dict/words"):
    try:
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            return {w.strip().lower() for w in f if w.strip().isalpha()}
    except OSError:
        return set()


def en_ingles(linea):
    w = re.findall(r"[A-Za-z]+", linea.lower())
    e, s = sum(x in _EN for x in w), sum(x in _ES for x in w)
    return e >= 2 and e > s
REGLAS_ORTOGRAFIA = ("MORFOLOGIK_RULE_ES", "HUNSPELL", "SPELLING")
MIN_REPETICION = 3          # una palabra «desconocida» escrita igual en 3 fichas o más se da por buena


def bloque_portal(md):
    i, j = md.find(INICIO), md.find(FIN)
    return md[i:j] if i != -1 and j > i else ""


def lineas_prosa(md):
    """Devuelve [(seccion, linea_cruda, linea_tapada)] con la prosa del bloque del portal."""
    seccion, salida = "", []
    for linea in bloque_portal(md).split("\n"):
        if linea.startswith("## "):
            seccion = linea[3:].strip()
            continue
        if not linea.strip() or _SALTAR.match(linea):
            continue
        tapada = linea
        for rx in _TAPAR:
            tapada = rx.sub(lambda m: " " * len(m.group(0)), tapada)
        if len(_PALABRA.findall(tapada)) >= 3:
            salida.append((seccion, linea, tapada))
    return salida


def _contexto(linea, ini, fin, margen=30):
    """Fragmento de la línea alrededor del error, cortado en límites de palabra."""
    a = max(0, ini - margen)
    while a > 0 and linea[a - 1] not in " \t":
        a -= 1
    b = min(len(linea), fin + margen)
    while b < len(linea) and linea[b] not in " \t":
        b += 1
    return a, b


def identificador(antes, despues):
    return hashlib.sha1(f"{antes}\n{despues}".encode()).hexdigest()[:12]


def es_ortografia(regla):
    return any(regla.startswith(p) for p in REGLAS_ORTOGRAFIA)


def palabras_conocidas(textos):
    """Palabras que aparecen escritas igual en MIN_REPETICION fichas o más."""
    c = Counter()
    for t in textos:
        c.update({w for w in _PALABRA.findall(t)})
    return {w for w, n in c.items() if n >= MIN_REPETICION}


_TILDES = {"\u0301"}           # tilde (acento agudo): lo único que el corrector puede poner o quitar


def solo_tilde(palabra, sugerencia):
    """True si la sugerencia solo pone o quita tildes: mismas letras, en el mismo orden y con las mismas mayúsculas.
    «vehiculo» -> «vehículo» o «dictámen» -> «dictamen» sí; «en caso que» -> «en caso de que» o «carga» -> «cargar» no."""
    def sin(t):
        return "".join(c for c in unicodedata.normalize("NFD", t) if c not in _TILDES)
    return palabra != sugerencia and sin(palabra) == sin(sugerencia)


def filtrar(match, palabra, conocidas, ingles=frozenset()):
    """True si el aviso de LanguageTool vale la pena mostrarlo: solo tildes, para no cambiar palabras de la fuente."""
    regla = match["regla"]
    if regla in REGLAS_FUERA or match["categoria"] not in CATEGORIAS or not match["sugerencias"]:
        return False
    if not palabra.strip() or any(ch.isdigit() for ch in palabra):
        return False
    if es_ortografia(regla):
        if palabra[0].isupper() or palabra in conocidas or len(palabra) < 3 or not _SOLO_LETRAS.match(palabra):
            return False
        if palabra.lower() in ingles:
            return False
    return solo_tilde(palabra, match["sugerencias"][0])


def hallazgos_de_nota(rel, md, revisar, conocidas, ingles=frozenset()):
    """revisar(texto) -> [{'offset','length','regla','categoria','mensaje','sugerencias'}]"""
    titulo = re.search(r'^titulo: "?(.*?)"?$', md, re.M)
    inst = re.search(r'^institucion: "\[\[[^|\]]*\|([^\]]*)\]\]"', md, re.M) or \
        re.search(r'^institucion: "?([^"\n\[]+)"?$', md, re.M)
    salida, vistos = [], set()
    lineas = lineas_prosa(md)
    if not lineas:
        return salida
    texto = "\n".join(t for _, _, t in lineas)
    inicios, pos = [], 0
    for _, _, t in lineas:
        inicios.append(pos)
        pos += len(t) + 1
    avisos = []
    for m in revisar(texto):
        k = max(i for i, p in enumerate(inicios) if p <= m["offset"])
        avisos.append((k, m))
    # renglones ilegibles: demasiadas palabras desconocidas
    desconocidas = Counter(k for k, m in avisos if es_ortografia(m["regla"]))
    for k, m in avisos:
        if en_ingles(lineas[k][1]):
            continue
        if desconocidas[k] and desconocidas[k] / max(1, len(_PALABRA.findall(lineas[k][2]))) > MAX_DESCONOCIDAS:
            continue
        seccion, cruda, _ = lineas[k]
        ini = m["offset"] - inicios[k]
        fin = ini + m["length"]
        palabra = cruda[ini:fin]
        if not filtrar(m, palabra, conocidas, ingles):
            continue
        a, b = _contexto(cruda, ini, fin)
        antes = cruda[a:b]
        despues = cruda[a:ini] + m["sugerencias"][0] + cruda[fin:b]
        if md.count(antes) < 1:
            continue
        hid = identificador(antes, despues)
        if hid in vistos:
            continue
        vistos.add(hid)
        salida.append({
            "id": hid, "nota": rel, "titulo": titulo.group(1) if titulo else os.path.basename(rel)[:-3],
            "institucion": inst.group(1).strip() if inst else rel.split("/")[1], "seccion": seccion,
            "antes": antes, "despues": despues, "palabra": palabra, "sugerencia": m["sugerencias"][0],
            "otras": m["sugerencias"][1:4], "regla": m["regla"], "mensaje": m["mensaje"],
        })
    return salida


def notas_tramite(raiz):
    base = os.path.join(raiz, CARPETA)
    for d, _, archivos in os.walk(base):
        for a in sorted(archivos):
            if not a.endswith(".md"):
                continue
            ruta = os.path.join(d, a)
            with open(ruta, encoding="utf-8") as f:
                md = f.read()
            if re.search(r'^tipo: "?tramite"?$', md, re.M):
                yield os.path.relpath(ruta, raiz).replace(os.sep, "/"), md


def revisor_languagetool():
    import language_tool_python
    lt = language_tool_python.LanguageTool("es", config={"maxTextLength": 200000})

    def revisar(texto, tope=50000):
        # LanguageTool no acepta textos muy largos: se revisa por pedazos de renglones completos
        if len(texto) > tope:
            salida, ini = [], 0
            while ini < len(texto):
                fin = texto.rfind("\n", ini, ini + tope)
                fin = len(texto) if ini + tope >= len(texto) else (fin + 1 if fin > ini else ini + tope)
                for m in revisar(texto[ini:fin], tope):
                    m["offset"] += ini
                    salida.append(m)
                ini = fin
            return salida
        return [{"offset": m.offset, "length": m.error_length if hasattr(m, "error_length") else m.errorLength,
                 "regla": m.rule_id if hasattr(m, "rule_id") else m.ruleId,
                 "categoria": m.category, "mensaje": m.message, "sugerencias": list(m.replacements)}
                for m in lt.check(texto)]
    return revisar, lt


def revisar_repo(raiz, revisar, muestra=0):
    notas = list(notas_tramite(raiz))
    conocidas = palabras_conocidas(bloque_portal(md) for _, md in notas)
    todos = []
    if muestra:
        import random
        random.seed(7)
        notas = random.sample(notas, min(muestra, len(notas)))
    ingles = diccionario_ingles()
    for rel, md in notas:
        todos += hallazgos_de_nota(rel, md, revisar, conocidas, ingles)
    return notas, agrupar(todos)


def agrupar(todos):
    """Un mismo texto con el mismo error en varias fichas queda como un solo hallazgo con todas sus fichas."""
    grupos = {}
    for h in todos:
        g = grupos.get(h["id"])
        if g is None:
            g = grupos[h["id"]] = {k: v for k, v in h.items() if k not in ("nota", "titulo")}
            g["notas"], g["titulos"] = [], []
        if h["nota"] not in g["notas"]:
            g["notas"].append(h["nota"])
            g["titulos"].append(h["titulo"])
    salida = list(grupos.values())
    salida.sort(key=lambda h: (h["institucion"], h["titulos"][0], h["id"]))
    return salida


def main(raiz, muestra=0):
    revisar, lt = revisor_languagetool()
    try:
        notas, todos = revisar_repo(raiz, revisar, muestra)
    finally:
        lt.close()
    if muestra:
        for h in todos:
            print(f"[{h['regla']}] «{h['palabra']}» -> «{h['sugerencia']}» | {len(h['notas'])} fichas | {h['antes'][:110]}")
        print(f"Muestra: {len(notas)} fichas, {len(todos)} posibles errores (no se guardó nada).")
        return
    os.makedirs(os.path.join(raiz, "revision"), exist_ok=True)
    with open(os.path.join(raiz, SALIDA), "w", encoding="utf-8") as f:
        import datetime
        json.dump({"fecha": datetime.date.today().isoformat(), "fichas_revisadas": len(notas), "hallazgos": todos},
                  f, ensure_ascii=False, indent=1)
    reglas = Counter(h["regla"] for h in todos)
    print(f"Revisión de textos: {len(notas)} fichas revisadas, {len(todos)} posibles errores.")
    for r, n in reglas.most_common(10):
        print(f"  {n:5d} {r}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("raiz", nargs="?", default=".")
    ap.add_argument("--muestra", type=int, default=0, help="revisar solo N fichas al azar y mostrar el resultado")
    a = ap.parse_args()
    main(a.raiz, a.muestra)
