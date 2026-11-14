"""
Compara las fichas de un sitio institucional contra los trámites que DIGER ya tiene de esa institución.
"""
import difflib
import json
import os
import re
import unicodedata

_PADRE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Catálogo de DIGER: si este código vive dentro del repositorio tramites-estado, se usa ese mismo repositorio.
REPO = os.environ.get("REPO_TRAMITES") or (
    _PADRE if os.path.exists(os.path.join(_PADRE, "estado", "catalogo.json")) else os.path.expanduser("~/tramites-estado"))
VACIAS = {"de", "del", "la", "las", "los", "el", "y", "o", "en", "para", "por", "a", "al", "con", "u", "e",
          "requisitos", "requisito", "solicitud", "tramite", "tramites", "formato", "formulario", "sar", "cnbs", "oncae"}
EQUIVALENTE = 0.75   # desde aquí se considera el mismo trámite (no se crea nota)
POSIBLE = 0.5        # entre POSIBLE y EQUIVALENTE: nota con enlace para revisar


def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def tokens(t):
    return {w for w in norm(t).split() if w not in VACIAS and len(w) > 1}


def similitud(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _plano(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for i in x for s in _plano(i)]
    if isinstance(x, dict):
        return [s for k in ("titulo", "texto", "lineas", "elementos", "contenido") if k in x for s in _plano(x[k])]
    return []


def tramites_diger(id_institucion):
    cat = os.path.join(REPO, "estado", "catalogo.json")
    if not id_institucion or not os.path.exists(cat):
        return []
    c = json.load(open(cat, encoding="utf-8"))
    res = []
    for tid, t in c["tramites"].items():
        if str(t.get("institucion")) != str(id_institucion) or t.get("estado_portal", "Vigente") != "Vigente":
            continue
        archivo = t["archivo"]
        titulo = re.sub(r"^TR-\d+\s+", "", os.path.basename(archivo)[:-3])
        req = ""
        f = os.path.join(REPO, "estado", "fichas", f"{tid}.json")
        if os.path.exists(f):
            d = json.load(open(f, encoding="utf-8"))
            for p in d.get("pestanas", []):
                if "requisit" in (p.get("clave", "") + str(p.get("titulo", ""))).lower():
                    req = "\n".join(_plano(p.get("contenido")))
        res.append({"id": tid, "titulo": titulo, "archivo": archivo[:-3], "requisitos": req})
    return res


def comparar(fichas, id_institucion):
    """Devuelve {id_local: {'nivel': 'equivalente'|'posible'|None, 'diger': {...}, 'similitud': x, 'requisitos': ...}}"""
    dig = tramites_diger(id_institucion)
    res = {}
    for f in fichas:
        mejor, puntaje = None, 0.0
        for d in dig:
            s = similitud(f.titulo, d["titulo"])
            if s > puntaje:
                mejor, puntaje = d, s
        nivel = "equivalente" if puntaje >= EQUIVALENTE else "posible" if puntaje >= POSIBLE else None
        req_sitio = next((v for k, v in f.secciones.items() if "requisit" in k.lower()), "")
        comp = "sin datos para comparar"
        if nivel and mejor["requisitos"] and req_sitio:
            r = difflib.SequenceMatcher(None, " ".join(sorted(tokens(req_sitio))),
                                        " ".join(sorted(tokens(mejor["requisitos"])))).ratio()
            comp = "coinciden" if r >= 0.8 else f"difieren (parecido {r:.0%})"
        if nivel == "equivalente" and comp.startswith("difieren"):
            nivel = "posible"  # mismo trámite, pero el sitio publica otros requisitos: se guarda la nota
        res[f.id_local] = {"nivel": nivel, "diger": mejor if nivel else None, "similitud": round(puntaje, 2),
                           "requisitos": comp, "req_sitio": req_sitio}
    return res, dig
