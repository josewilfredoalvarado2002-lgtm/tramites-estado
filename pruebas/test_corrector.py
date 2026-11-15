"""Pruebas del corrector, capa 2: revisor (sin LanguageTool) y el flujo de marcar y aplicar en el puente."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "puente"))
from corrector import capa2 as C  # noqa: E402
import puente_tramites as P  # noqa: E402

FICHA = """---
tipo: "tramite"
titulo: "Placa de vehiculo"
institucion: "[[10 Trámites del Estado/IP/IP|Instituto de la Propiedad]]"
---
<!-- portal:inicio -->
# Placa de vehiculo

| Dato | Valor |
| --- | --- |
| Título | Placa de vehiculo |

## Requisitos

- Copia de la boleta de revision del vehiculo, pagada en www.ip.gob.hn el 12/03/2024.
- Constancia del Ministerio Publico cuando el vehiculo fue robado.
<!-- portal:fin -->

## Notas propias

Mi nota: el vehiculo del cliente.
"""


def falso_revisor(errores):
    """Imita a LanguageTool: marca cada palabra de `errores` con su corrección."""
    def revisar(texto):
        out = []
        for palabra, (sug, regla, cat) in errores.items():
            k = texto.find(palabra)
            while k != -1:
                out.append({"offset": k, "length": len(palabra), "regla": regla, "categoria": cat,
                            "mensaje": "Posible error", "sugerencias": [sug]})
                k = texto.find(palabra, k + 1)
        return out
    return revisar


class Revisor(unittest.TestCase):
    def test_solo_prosa_del_portal(self):
        lineas = C.lineas_prosa(FICHA)
        crudas = [c for _, c, _ in lineas]
        self.assertTrue(all("Mi nota" not in c for c in crudas))          # Notas propias no se revisan
        self.assertTrue(all(not c.startswith("|") for c in crudas))       # tablas tampoco
        tapada = next(t for _, c, t in lineas if "www" in c)
        self.assertNotIn("www.ip.gob.hn", tapada)
        self.assertNotIn("12/03/2024", tapada)
        self.assertEqual(len(tapada), len(next(c for _, c, _ in lineas if "www" in c)))  # mismas posiciones

    def test_hallazgos_y_filtros(self):
        revisar = falso_revisor({"vehiculo": ("vehículo", "DIACRITICS_02", "TYPOS"),
                                 "revision": ("revisión", "MORFOLOGIK_RULE_ES", "TYPOS"),
                                 "Publico": ("Público", "DIACRITICS_VERB_N_ADJ", "TYPOS"),
                                 "Copia": ("Copiá", "MORFOLOGIK_RULE_ES", "TYPOS"),       # mayúscula: nombre propio
                                 "pagada": ("pagado", "ESTILO", "STYLE")})                 # estilo: fuera
        hs = C.hallazgos_de_nota("10 Trámites del Estado/IP/Placa.md", FICHA, revisar, conocidas=set())
        palabras = sorted(h["palabra"] for h in hs)
        self.assertEqual(palabras, ["Publico", "revision", "vehiculo", "vehiculo"])
        for h in hs:
            self.assertIn(h["antes"], FICHA)
            self.assertEqual(h["despues"], h["antes"].replace(h["palabra"], h["sugerencia"], 1))

    def test_palabra_repetida_en_muchas_fichas_se_da_por_buena(self):
        revisar = falso_revisor({"revision": ("revisión", "MORFOLOGIK_RULE_ES", "TYPOS")})
        hs = C.hallazgos_de_nota("x.md", FICHA, revisar, conocidas={"revision"})
        self.assertEqual(hs, [])

    def test_ingles_y_renglones_ilegibles_no_se_marcan(self):
        md = FICHA.replace("- Constancia del Ministerio", "- The lifeboat is ready and the crew is on deck.\n"
                           "- $UWtFXOR &DGDSXHUWR WHUPLQDO SODWDIRUPD revision\n- Constancia del Ministerio")
        revisar = falso_revisor({"lifeboat": ("lifting", "MORFOLOGIK_RULE_ES", "TYPOS"),
                                 "WHUPLQDO": ("terminal", "MORFOLOGIK_RULE_ES", "TYPOS"),
                                 "SODWDIRUPD": ("plataforma", "MORFOLOGIK_RULE_ES", "TYPOS"),
                                 "revision": ("revisión", "MORFOLOGIK_RULE_ES", "TYPOS"),
                                 "crew": ("cree", "MORFOLOGIK_RULE_ES", "TYPOS")})
        hs = C.hallazgos_de_nota("x.md", md, revisar, set(), ingles={"crew"})
        # solo queda «revision» de la línea en español; ni el inglés ni el renglón revuelto
        self.assertEqual(len(hs), 1)
        self.assertIn("boleta de revision", hs[0]["antes"])

    def test_agrupa_el_mismo_texto_en_varias_fichas(self):
        revisar = falso_revisor({"Publico": ("Público", "DIACRITICS_VERB_N_ADJ", "TYPOS")})
        a = C.hallazgos_de_nota("10 Trámites del Estado/IP/A.md", FICHA, revisar, set())
        b = C.hallazgos_de_nota("10 Trámites del Estado/IP/B.md", FICHA, revisar, set())
        g = C.agrupar(a + b)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["notas"], ["10 Trámites del Estado/IP/A.md", "10 Trámites del Estado/IP/B.md"])


class MarcarYAplicar(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.repo = os.path.join(self.base, "repo")
        self.boveda = os.path.join(self.base, "boveda")
        self.rel = "10 Trámites del Estado/IP/Placa.md"
        os.makedirs(os.path.join(self.repo, "10 Trámites del Estado", "IP"))
        os.makedirs(os.path.join(self.repo, "revision"))
        os.makedirs(os.path.join(self.boveda, ".casedeck"))
        with open(os.path.join(self.repo, self.rel), "w", encoding="utf-8") as f:
            f.write(FICHA)
        revisar = falso_revisor({"Publico": ("Público", "DIACRITICS_VERB_N_ADJ", "TYPOS"),
                                 "revision": ("revisión", "MORFOLOGIK_RULE_ES", "TYPOS")})
        hs = C.agrupar(C.hallazgos_de_nota(self.rel, FICHA, revisar, set()))
        with open(os.path.join(self.repo, P.HALLAZGOS), "w", encoding="utf-8") as f:
            json.dump({"fecha": "2026-11-15", "fichas_revisadas": 1, "hallazgos": hs}, f, ensure_ascii=False)
        self.hs = {h["palabra"]: h for h in hs}
        self.estado = {}

    def tearDown(self):
        shutil.rmtree(self.base)

    def nota(self):
        with open(os.path.join(self.boveda, P.NOTA_REVISION), encoding="utf-8") as f:
            return f.read()

    def ficha(self):
        with open(os.path.join(self.boveda, self.rel), encoding="utf-8") as f:
            return f.read()

    def correr(self, ahora=None):
        corr = P.corrector(self.repo, self.boveda, ahora=ahora)
        P.sincronizar(self.repo, self.boveda, self.estado, gracia_min=0, correcciones=corr)
        return corr

    def marcar(self, accion, palabra, ahora):
        hid = self.hs[palabra]["id"]
        lineas = []
        for ln in self.nota().split("\n"):
            if ln.endswith(f"%%{accion}:{hid}%%"):
                ln = ln.replace("- [ ]", "- [x]", 1)
            lineas.append(ln)
        ruta = os.path.join(self.boveda, P.NOTA_REVISION)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        os.utime(ruta, (ahora - 600, ahora - 600))        # editada hace 10 minutos

    def test_flujo_completo(self):
        self.correr()
        self.assertIn("**Pendientes:** 2", self.nota())
        self.assertIn("Ministerio Publico", self.ficha())                 # nada cambia sin marcar
        ahora = time.time()
        self.marcar("corregir", "Publico", ahora)
        self.marcar("dejar", "revision", ahora)
        # la ficha de la bóveda tiene notas propias que no se pueden perder
        self.correr(ahora=ahora)
        f = self.ficha()
        self.assertIn("Ministerio Público", f)
        self.assertIn("revision del vehiculo", f)                         # «dejar como está»
        self.assertIn("Correcciones hechas en Case Deck", f)
        self.assertIn("«Publico» → «Público»", f)
        self.assertIn("Mi nota: el vehiculo del cliente.", f)            # Notas propias intactas
        self.assertIn("No hay nada pendiente.", self.nota())
        with open(os.path.join(self.boveda, P.DECISIONES), encoding="utf-8") as fh:
            dec = json.load(fh)
        self.assertEqual(len(dec["corregir"]), 1)
        self.assertEqual(len(dec["dejar"]), 1)
        # el repositorio sigue con el texto original
        with open(os.path.join(self.repo, self.rel), encoding="utf-8") as fh:
            self.assertIn("Ministerio Publico", fh.read())

    def test_las_dos_casillas_no_hacen_nada(self):
        self.correr()
        ahora = time.time()
        self.marcar("corregir", "Publico", ahora)
        self.marcar("dejar", "Publico", ahora)
        self.correr(ahora=ahora)
        self.assertIn("Ministerio Publico", self.ficha())

    def test_nota_editada_hace_poco_no_se_toca(self):
        self.correr()
        ahora = time.time()
        self.marcar("corregir", "Publico", ahora)
        os.utime(os.path.join(self.boveda, P.NOTA_REVISION), (ahora - 10, ahora - 10))
        antes = self.nota()
        self.correr(ahora=ahora)
        self.assertEqual(self.nota(), antes)
        self.assertIn("Ministerio Publico", self.ficha())

    def test_correccion_sobrevive_a_un_cambio_de_la_fuente(self):
        self.correr()
        ahora = time.time()
        self.marcar("corregir", "Publico", ahora)
        self.correr(ahora=ahora)
        with open(os.path.join(self.repo, self.rel), "w", encoding="utf-8") as fh:
            fh.write(FICHA.replace("pagada", "ya pagada"))
        self.correr(ahora=ahora + 10)
        f = self.ficha()
        self.assertIn("ya pagada", f)
        self.assertIn("Ministerio Público", f)


if __name__ == "__main__":
    unittest.main()
