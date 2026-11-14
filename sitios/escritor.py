"""
Escribe las fichas como notas de Obsidian, con el mismo contrato que DIGER y San Pedro Sula:
propiedades arriba, copia del sitio entre <!-- portal:inicio --> y <!-- portal:fin -->,
y "## Notas propias" debajo, que nunca se toca.

Carpeta: 10 Trámites del Estado/<Institución>/Sitio institucional/
"""
import json
import os
import re
from datetime import datetime

INICIO, FIN = "<!-- portal:inicio -->", "<!-- portal:fin -->"
RAIZ = "10 Trámites del Estado"


def q(t):
    return json.dumps(t if t not in (None, "") else "No consta en el sitio", ensure_ascii=False)


def nombre_archivo(t, maximo=110):
    t = re.sub(r'[\\/:*?"<>|#^\[\]]', "", t or "")
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:maximo].rstrip(" .") or "sin título"


def md(texto):
    out = []
    for l in (texto or "").split("\n"):
        l = l.rstrip()
        if l.startswith(("#", "|", ">")):
            l = "\\" + l
        if l.startswith("• "):
            l = "- " + l[2:]
        out.append(l)
    t = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


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


class Escritor:
    def __init__(self, boveda, fuente, registro_inst):
        self.boveda = boveda
        self.f = fuente
        self.carpeta_inst = os.path.join(boveda, RAIZ, fuente["carpeta"])
        self.carpeta = os.path.join(self.carpeta_inst, "Sitio institucional")
        nota_inst = os.path.join(self.carpeta_inst, fuente["carpeta"] + ".md")
        self.enlace_inst = (f'"[[{RAIZ}/{fuente["carpeta"]}/{fuente["carpeta"]}|{fuente["nombre"]}]]"'
                            if os.path.exists(nota_inst) else q(fuente["nombre"]))
        m = registro_inst["mejor"]
        senales = "".join(x for x, k in (("G", "senal_gob"), ("D", "senal_diger"), ("I", "senal_identidad"),
                                          ("E", "senal_enlazado")) if m.get(k))
        self.dominio = m["dominio_final"]
        self.verificacion = f"{registro_inst['estado']} ({senales})"

    def existentes(self, siglas):
        res = {}
        if os.path.isdir(self.carpeta):
            for n in os.listdir(self.carpeta):
                m = re.match(rf"{re.escape(siglas)}-(\w+) ", n)
                if m and n.endswith(".md"):
                    res[m.group(1)] = os.path.join(self.carpeta, n)
        return res

    def propiedades(self, f, h, ahora, comp):
        L = ["---",
             f'tipo: "{f.tipo}"',
             'fuente: "sitio_institucional"',
             f"id_sitio: {q(f.id_local)}",
             f"titulo: {q(f.titulo)}",
             "aliases:", f"  - {q(f.titulo)}",
             f"institucion: {self.enlace_inst}",
             f"categoria: {q(f.categoria)}",
             f'calidad: "{f.calidad()}"',
             f"url_ficha: {q(f.url_ficha)}"]
        docs = [d["url"] for d in f.documentos]
        L += ["documentos:"] + [f"  - {q(u)}" for u in docs] if docs else ["documentos: []"]
        L += [f"actualizado_sitio: {q(f.actualizado_fuente)}",
              f'dominio_verificado: "{self.dominio}"',
              f"verificacion_dominio: {q(self.verificacion)}",
              f"extraido: {ahora:%Y-%m-%dT%H:%M}",
              f'huella: "{h}"',
              'estado_sitio: "Vigente"']
        if comp and comp["nivel"] == "posible":
            L.append(f'posible_equivalente_diger: "[[{comp["diger"]["archivo"]}|{comp["diger"]["titulo"]}]]"')
        L.append("---")
        return "\n".join(L)

    def cuerpo(self, f, ahora, comp):
        L = [INICIO, f"# {f.titulo}", "",
             f"> [!info] Copia del sitio oficial de {self.f['nombre']} (`{self.dominio}`, {self.verificacion}), "
             "tal como aparece en el sitio. No se resumió, completó ni verificó. El crawler reescribe este bloque "
             "cuando el sitio cambia; tus anotaciones van en Notas propias.", ""]
        if comp and comp["nivel"] == "posible":
            L += [f"> [!question] Puede ser el mismo trámite que [[{comp['diger']['archivo']}|{comp['diger']['titulo']}]] "
                  f"de DIGER (parecido de títulos {comp['similitud']:.0%}). Revisalo antes de usar una u otra.", ""]
        if f.avisos:
            L += ["> [!warning] Avisos de la extracción"] + [f"> - {a}" for a in f.avisos] + [""]
        L += ["## Cabecera", "", "| Dato | Según el sitio |", "| --- | --- |",
              f"| Institución | {self.f['nombre']} |", f"| Categoría | {f.categoria or 'No consta en el sitio'} |",
              f"| Última actualización que muestra el sitio | {f.actualizado_fuente or 'No consta en el sitio'} |",
              f"| Calidad de la extracción | {f.calidad().replace('_', ' ')} |", ""]
        for k, v in f.secciones.items():
            L += [f"## {k}", "", md(v), ""]
        if f.documentos:
            L += ["## Documentos", ""]
            for d in f.documentos:
                extra = f" — {d['aviso']}" if d.get("aviso") else ""
                L.append(f"- [{d['nombre']}]({d['url'].replace(' ', '%20')}){extra}")
            L.append("")
        L += ["## Fuente", "", f"- Ficha: {f.url_ficha}",
              f"- Fecha y hora de extracción: {ahora:%Y-%m-%d %H:%M} (hora de Honduras, UTC-6)", FIN]
        return "\n".join(L)

    def escribir_fichas(self, fichas, comparacion, completo):
        ahora = datetime.now()
        siglas = self.f["siglas"]
        existentes = self.existentes(siglas)
        nuevas, cambiadas, iguales, omitidas = [], [], 0, []
        vistos = set()
        for f in fichas:
            comp = comparacion.get(f.id_local)
            if comp and comp["nivel"] == "equivalente":
                omitidas.append((f, comp))
                continue
            vistos.add(f.id_local)
            h = __import__("nucleo").huella(f.contenido())
            ruta_vieja = existentes.get(f.id_local)
            anterior = leer(ruta_vieja) if ruta_vieja else None
            if anterior and f'huella: "{h}"' in anterior and 'estado_sitio: "Vigente"' in anterior:
                iguales += 1
                continue
            ruta = ruta_vieja or os.path.join(self.carpeta, f"{siglas}-{f.id_local} {nombre_archivo(f.titulo)}.md")
            notas = "## Notas propias\n"
            if anterior and FIN in anterior:
                resto = anterior.split(FIN, 1)[1].strip("\n")
                notas = (resto + "\n") if resto else notas
            escribir(ruta, f"{self.propiedades(f, h, ahora, comp)}\n{self.cuerpo(f, ahora, comp)}\n\n{notas}")
            (cambiadas if anterior else nuevas).append(f)
        retiradas = []
        if completo:
            for idl, ruta in existentes.items():
                if idl not in vistos:
                    t = leer(ruta)
                    if t and 'estado_sitio: "Vigente"' in t:
                        escribir(ruta, t.replace('estado_sitio: "Vigente"', 'estado_sitio: "Ya no aparece en el sitio"', 1))
                        retiradas.append(os.path.basename(ruta)[:-3])
        return nuevas, cambiadas, iguales, omitidas, retiradas

    def enlace(self, f):
        siglas = self.f["siglas"]
        ruta = self.existentes(siglas).get(f.id_local)
        nombre = os.path.basename(ruta)[:-3] if ruta else f"{siglas}-{f.id_local} {nombre_archivo(f.titulo)}"
        return f"[[{RAIZ}/{self.f['carpeta']}/Sitio institucional/{nombre}|{f.titulo}]]"

    def indice(self, fichas, comparacion, dig, resultado, errores, rechazadas):
        ahora = datetime.now()
        nuevas, cambiadas, iguales, omitidas, retiradas = resultado
        siglas, nombre = self.f["siglas"], self.f["nombre"]
        creadas = [f for f in fichas if not (comparacion.get(f.id_local) or {}).get("nivel") == "equivalente"]
        from collections import Counter
        cal = Counter(f.calidad() for f in creadas)
        L = ["---", 'tipo: "indice_sitio_institucional"', f'institucion: "{nombre}"',
             f'dominio_verificado: "{self.dominio}"', f"actualizado: {ahora:%Y-%m-%dT%H:%M}", "---",
             f"# {siglas} — Sitio institucional", "",
             f"> [!info] Trámites y formatos copiados del sitio oficial `{self.dominio}` ({self.verificacion}). "
             "Se reescribe en cada corrida.", "",
             "## Resumen", "",
             f"- Fichas leídas en el sitio: **{len(fichas)}**",
             f"- Notas en esta carpeta: **{len(creadas)}** "
             f"(completas {cal.get('completo', 0)}, solo requisitos {cal.get('solo_requisitos', 0)}, "
             f"sin requisitos {cal.get('sin_requisitos', 0)}, sin contenido {cal.get('sin_contenido', 0)})",
             f"- Ya estaban en DIGER (no se duplicaron): **{len(omitidas)}**",
             f"- Trámites de DIGER para esta institución: **{len(dig)}**",
             f"- Errores de lectura: **{len(errores)}** · enlaces rechazados por estar fuera del dominio verificado: "
             f"**{len(set(rechazadas))}**", ""]
        if omitidas:
            L += ["## Ya estaban en DIGER", "",
                  "No se creó nota para estos: la ficha de DIGER es la principal. La columna de requisitos "
                  "dice si el sitio de la institución publica lo mismo.", "",
                  "| Sitio institucional | Ficha DIGER | Parecido del título | Requisitos |", "| --- | --- | --- | --- |"]
            for f, c in omitidas:
                L.append(f"| [{f.titulo}]({f.url_ficha}) | [[{c['diger']['archivo']}|{c['diger']['titulo']}]] | "
                         f"{c['similitud']:.0%} | {c['requisitos']} |")
            L.append("")
            for f, c in omitidas:
                if c["requisitos"].startswith("difieren"):
                    L += [f"> [!compare]- {f.titulo}: requisitos según el sitio de {siglas}",
                          *[f"> {l}" for l in md(c["req_sitio"]).split("\n")], "",
                          f"> [!compare]- {c['diger']['titulo']}: requisitos según DIGER",
                          *[f"> {l}" for l in md(c["diger"]["requisitos"]).split("\n")], ""]
        L += ["## Notas por categoría", ""]
        por_cat = {}
        for f in creadas:
            por_cat.setdefault(f.categoria or ("Formatos" if f.tipo == "formato" else "Páginas de trámites"), []).append(f)
        for cat in sorted(por_cat):
            L += [f"### {cat}", ""]
            for f in sorted(por_cat[cat], key=lambda x: x.titulo):
                marca = "" if f.calidad() in ("completo", "solo_requisitos", "formato_con_texto") else f" — *{f.calidad().replace('_', ' ')}*"
                L.append(f"- {self.enlace(f)}{marca}")
            L.append("")
        if errores:
            L += ["## Errores de lectura", ""] + [f"- {e}" for e in errores] + [""]
        if rechazadas:
            L += ["## Enlaces rechazados (fuera del dominio verificado)", ""] + \
                 [f"- `{u}`" for u in sorted(set(rechazadas))[:50]] + [""]
        escribir(os.path.join(self.carpeta, f"{siglas} — Sitio institucional.md"), "\n".join(L) + "\n")

        # registro de cambios
        ruta = os.path.join(self.carpeta, f"Registro de cambios {siglas}.md")
        previo = leer(ruta) or f"# Registro de cambios {siglas}\n\nCada corrida agrega una entrada arriba.\n"
        if not previo or (nuevas and not cambiadas and iguales == 0 and not retiradas and "## " not in previo):
            entrada = f"## {ahora:%Y-%m-%d %H:%M}\n\nCarga inicial: {len(nuevas)} notas.\n"
        elif not (nuevas or cambiadas or retiradas):
            entrada = f"## {ahora:%Y-%m-%d %H:%M}\n\nSin cambios en el sitio.\n"
        else:
            E = [f"## {ahora:%Y-%m-%d %H:%M}", ""]
            for et, lista in (("Nuevas", nuevas), ("Actualizadas", cambiadas)):
                if lista:
                    E += [f"**{et} ({len(lista)})**", ""] + [f"- {self.enlace(f)}" for f in lista] + [""]
            if retiradas:
                E += [f"**Ya no aparecen en el sitio ({len(retiradas)})**", ""] + [f"- [[{n}]]" for n in retiradas] + [""]
            entrada = "\n".join(E)
        cabeza, _, cuerpo = previo.partition("\n## ")
        escribir(ruta, f"{cabeza.rstrip()}\n\n{entrada}\n" + (("## " + cuerpo) if cuerpo else ""))
