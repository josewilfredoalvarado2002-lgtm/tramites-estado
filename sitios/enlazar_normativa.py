"""
Enlaza cada trámite con las normas de La Gaceta que cita.

Recorre las notas de "10 Trámites del Estado" (las de DIGER y las de los sitios), busca las citas
"Decreto / Acuerdo / Resolución <número>-<año>" en el texto copiado del portal o del sitio, y las
busca entre los actos de "11 Normativa" (los que el crawler de La Gaceta ya cargó).

Escribe, dentro del bloque del portal, la sección "Normas citadas":
  - enlace a la nota del acto cuando hay una sola coincidencia segura;
  - "posible" cuando el número coincide pero el emisor no se puede confirmar (los números se repiten
    entre secretarías: el Acuerdo 224-2025 de una no es el de otra);
  - "no está en la colección" cuando el acto es anterior a lo que cubre La Gaceta en el repositorio
    o no aparece en ella.
No inventa nada: solo relaciona números que aparecen escritos en los dos lados.

Los enlaces usan el nombre de la nota ([[Decreto 45-2026 (Gaceta 37106)]]), que es el mismo en el
repositorio y en la bóveda, así que funcionan con la disposición de carpetas de la bóveda.

Uso:  python3 sitios/enlazar_normativa.py [carpeta_del_repositorio]
"""
import os
import re
import sys
import unicodedata
from collections import defaultdict

TRAMITES = "10 Trámites del Estado"
NORMATIVA = "11 Normativa"
FIN = "<!-- portal:fin -->"
INI_B, FIN_B = "<!-- normas:inicio -->", "<!-- normas:fin -->"
_BLOQUE = re.compile(r"\n*" + re.escape(INI_B) + r".*?" + re.escape(FIN_B) + r"\n*", re.S)

CITA = re.compile(
    r"\b(Decreto|Acuerdo|Resoluci[oó]n)"
    r"(?:\s+(Ejecutivo|Legislativo|Ministerial|Presidencial|Interinstitucional|Municipal))?"
    r"\s*(?:No\s*\.?|N[°º]\s*\.?|Nro\s*\.?|N[uú]mero)?\s*"
    r"([A-Z0-9]+(?:-[A-Z0-9]+)*-((?:19|20)\d{2}))\b", re.I)
# grupos: 1 tipo, 2 calificativo (Legislativo, Ejecutivo...), 3 número, 4 año
_VACIAS = {"de", "del", "la", "las", "los", "el", "y", "en", "e", "para", "secretaria", "estado", "despacho",
           "nacional", "general", "direccion", "republica", "honduras", "instituto", "comision", "oficina"}


def _nfc(t):
    return unicodedata.normalize("NFC", t)


def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


def norm_numero(n):
    """«0155-ARSA-2025» y «155-arsa-2025» son el mismo número."""
    return "-".join(p.lstrip("0") or "0" for p in n.upper().split("-"))


def tipo_corto(t):
    t = _sin_tildes(t)
    return "resolucion" if t.startswith("resol") else t[:7]   # decreto | acuerdo | resolucion


def palabras(t):
    return {w for w in re.findall(r"[a-z0-9]+", _sin_tildes(t)) if len(w) > 2 and w not in _VACIAS}


def _prop(texto, clave):
    m = re.search(rf'^{clave}: "?(.*?)"?$', texto, re.M)
    return m.group(1) if m else ""


def indice_normativa(repo):
    idx, anios = defaultdict(list), []
    for raiz, _, archivos in os.walk(os.path.join(repo, NORMATIVA)):
        for a in archivos:
            if not a.endswith(".md"):
                continue
            with open(os.path.join(raiz, a), encoding="utf-8") as f:
                cab = f.read(2000)
            tipo, numero = _prop(cab, "tipo_acto"), _prop(cab, "numero")
            if not re.search(r"\d", numero):
                # «Otro acto» sin número: el lector de La Gaceta no reconoció el encabezado (p. ej. «ACUERDO
                # SEN-119-2022», sin «No.»), pero el título lo trae. Solo si el título nombra un único acto.
                enc = citas(_prop(cab, "titulo"))
                if len(enc) != 1:
                    continue
                (_, numero), tipo = enc[0][0], enc[0][1].split()[0]
            if not tipo or not numero:
                continue
            m = re.search(r"((?:19|20)\d{2})", _prop(cab, "gaceta_fecha"))
            if m:
                anios.append(int(m.group(1)))
            idx[(tipo_corto(tipo), norm_numero(numero))].append({
                "nota": _nfc(a[:-3]), "emisor": _prop(cab, "emisor"), "fecha": _prop(cab, "gaceta_fecha"),
                "numero": numero, "tipo": tipo})
    return idx, (min(anios) if anios else None)


def institucion_de(texto):
    inst = _prop(texto, "institucion")
    m = re.search(r"\|([^\]]+)\]\]", inst)
    return m.group(1) if m else re.sub(r"[\[\]]", "", inst)


def _confirma(acto, cita_numero, inst, calif="", unico=False):
    """El emisor del acto es la institución del trámite (por nombre o por las siglas del número), o es un
    decreto legislativo: los emite el Congreso y su número no se repite en el año."""
    if acto["tipo"].lower().startswith("decreto") and unico and "legislativo" in _sin_tildes(acto["emisor"]) \
            and _sin_tildes(calif) in ("", "legislativo"):
        return True
    pi, pe = palabras(inst), palabras(acto["emisor"])
    if len(pi & pe) >= 2 or (pi and pi <= pe):
        return True
    siglas = [p for p in cita_numero.split("-") if p.isalpha()]
    return bool(siglas)   # «SEN-060-2025», «0155-ARSA-2025»: el número ya dice quién lo emitió


def citas(texto):
    vistas, res = set(), []
    for m in CITA.finditer(texto):
        clave = (tipo_corto(m.group(1)), norm_numero(m.group(3)))
        if clave in vistas:
            continue
        vistas.add(clave)
        tipo = m.group(1).capitalize().replace("Resolucion", "Resolución")
        res.append((clave, tipo + (" " + m.group(2).capitalize() if m.group(2) else ""), m.group(3), int(m.group(4)),
                    m.group(2) or ""))
    return res


def bloque(texto, idx, desde):
    base = _BLOQUE.sub("\n\n", texto)
    portal = base.split(FIN, 1)[0]
    lista = citas(portal)
    if not lista:
        return None
    inst = institucion_de(texto)
    L = [INI_B, "## Normas citadas", "",
         f"> [!info] Decretos, acuerdos y resoluciones que menciona el texto de arriba, buscados por número entre "
         f"los actos de La Gaceta que están en la bóveda (publicados desde {desde or '—'}). «Posible» quiere decir que "
         "el número coincide pero no se pudo confirmar que lo haya emitido esta institución: revisalo antes de usarlo.",
         ""]
    for clave, tipo, numero, anio, calif in lista:
        actos = idx.get(clave, [])
        seguros = [a for a in actos if _confirma(a, clave[1], inst, calif, unico=len(actos) == 1)]
        nombre = f"{tipo} {numero}"
        if len(seguros) == 1:
            a = seguros[0]
            L.append(f"- {nombre} → [[{a['nota']}]] (La Gaceta del {a['fecha']}; emisor: {a['emisor'] or 'no consta'})")
        elif actos:
            pos = seguros or actos
            enl = "; ".join(f"[[{a['nota']}]] ({a['emisor'] or 'emisor no consta'})" for a in pos[:4])
            L.append(f"- {nombre} → posible: {enl}")
        elif desde and anio < desde:
            L.append(f"- {nombre} → anterior a {desde}: no está en la colección de La Gaceta de la bóveda")
        else:
            L.append(f"- {nombre} → no aparece en la colección de La Gaceta de la bóveda")
    L.append(FIN_B)
    return "\n".join(L)


def enlazar(repo):
    idx, desde = indice_normativa(repo)
    cambiadas = con_citas = enlaces = 0
    for raiz, _, archivos in os.walk(os.path.join(repo, TRAMITES)):
        for a in archivos:
            if not a.endswith(".md"):
                continue
            ruta = os.path.join(raiz, a)
            with open(ruta, encoding="utf-8") as f:
                texto = f.read()
            if FIN not in texto or not texto.startswith("---"):
                continue
            nuevo_b = bloque(texto, idx, desde)
            sin = _BLOQUE.sub("\n\n", texto).replace("\n\n\n" + FIN, "\n\n" + FIN)
            if nuevo_b:
                con_citas += 1
                enlaces += nuevo_b.count("→ [[")
                antes, despues = sin.split(FIN, 1)
                nuevo = antes.rstrip("\n") + "\n\n" + nuevo_b + "\n" + FIN + despues
            else:
                nuevo = sin
            if nuevo != texto:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(nuevo)
                cambiadas += 1
    print(f"Normas citadas: {con_citas} trámites citan normas, {enlaces} enlaces seguros a La Gaceta, "
          f"{cambiadas} notas actualizadas (colección desde {desde}).")
    return cambiadas


if __name__ == "__main__":
    enlazar(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
