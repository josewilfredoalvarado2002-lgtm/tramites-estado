"""Árbol HTML mínimo sobre html.parser de la biblioteca estándar.

Solo lo necesario para leer el portal: buscar por etiqueta, clase, id o atributo,
y obtener el texto. No depende de paquetes externos.
"""
from html.parser import HTMLParser

VACIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
          "param", "source", "track", "wbr"}


class Nodo:
    __slots__ = ("tag", "attrs", "hijos", "padre")

    def __init__(self, tag, attrs=None, padre=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.hijos = []
        self.padre = padre

    # -- consultas -----------------------------------------------------------
    @property
    def clases(self):
        return set((self.attrs.get("class") or "").split())

    def get(self, nombre, defecto=None):
        v = self.attrs.get(nombre)
        return defecto if v is None else v

    def elementos(self):
        """Recorre todos los elementos descendientes en orden del documento."""
        for h in self.hijos:
            if isinstance(h, Nodo):
                yield h
                yield from h.elementos()

    def buscar(self, tag=None, clase=None, id=None, attr=None, directos=False):
        fuente = (h for h in self.hijos if isinstance(h, Nodo)) if directos else self.elementos()
        salida = []
        for n in fuente:
            if tag and n.tag != tag:
                continue
            if clase and clase not in n.clases:
                continue
            if id and n.attrs.get("id") != id:
                continue
            if attr and attr not in n.attrs:
                continue
            salida.append(n)
        return salida

    def primero(self, **kw):
        r = self.buscar(**kw)
        return r[0] if r else None

    def texto(self, excluir_clases=()):
        """Texto crudo de todos los descendientes (entidades ya decodificadas)."""
        partes = []
        for h in self.hijos:
            if isinstance(h, Nodo):
                if excluir_clases and h.clases & set(excluir_clases):
                    continue
                if h.tag in ("script", "style"):
                    continue
                partes.append(h.texto(excluir_clases))
            else:
                partes.append(h)
        return "".join(partes)


class _Constructor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("#documento")
        self.actual = self.raiz

    def handle_starttag(self, tag, attrs):
        n = Nodo(tag, attrs, self.actual)
        self.actual.hijos.append(n)
        if tag not in VACIAS:
            self.actual = n

    def handle_startendtag(self, tag, attrs):
        self.actual.hijos.append(Nodo(tag, attrs, self.actual))

    def handle_endtag(self, tag):
        n = self.actual
        while n is not None and n.tag != tag:
            n = n.padre
        if n is not None and n.padre is not None:
            self.actual = n.padre

    def handle_data(self, data):
        self.actual.hijos.append(data)


def analizar(html: str) -> Nodo:
    c = _Constructor()
    c.feed(html)
    c.close()
    return c.raiz


def lineas(texto: str):
    """Divide en renglones, quita espacios sobrantes de cada uno y descarta los vacíos.
    No cambia palabras ni puntuación."""
    if not texto:
        return []
    t = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    salida = []
    for r in t.split("\n"):
        r = " ".join(r.split())
        if r:
            salida.append(r)
    return salida


def texto_unico(texto: str) -> str:
    return " ".join(lineas(texto))
