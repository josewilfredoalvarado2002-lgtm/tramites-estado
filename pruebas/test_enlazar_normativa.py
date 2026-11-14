import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sitios"))
import enlazar_normativa as en  # noqa: E402

NORMA = '---\ntipo: "norma"\ntipo_acto: "{t}"\nnumero: "{n}"\nemisor: "{e}"\ngaceta_fecha: "2026-03-28"\n---\n'
TRAMITE = ('---\ntipo: "tramite"\ninstitucion: "[[x|Secretaría de Trabajo y Seguridad Social]]"\n---\n'
           '<!-- portal:inicio -->\n# T\n\n{cuerpo}\n<!-- portal:fin -->\n\n## Notas propias\nmío\n')


class EnlazarNormativa(unittest.TestCase):
    def armar(self, cuerpo, normas):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, en.NORMATIVA, "Decretos", "2026"))
        os.makedirs(os.path.join(d, en.TRAMITES, "STSS"))
        for nombre, (t, n, e) in normas.items():
            with open(os.path.join(d, en.NORMATIVA, "Decretos", "2026", nombre + ".md"), "w", encoding="utf-8") as f:
                f.write(NORMA.format(t=t, n=n, e=e))
        ruta = os.path.join(d, en.TRAMITES, "STSS", "T.md")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(TRAMITE.format(cuerpo=cuerpo))
        return d, ruta

    def leer(self, ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read()

    def test_decreto_legislativo_enlazado_e_idempotente(self):
        d, ruta = self.armar("Según el Decreto Legislativo No. 045-2026 y el Decreto 170-2016.",
                             {"Decreto 45-2026 (Gaceta 37106)": ("Decreto", "45-2026", "Poder Legislativo")})
        en.enlazar(d)
        t = self.leer(ruta)
        self.assertIn("→ [[Decreto 45-2026 (Gaceta 37106)]]", t)
        self.assertIn("Decreto 170-2016 → anterior a 2026", t)
        self.assertTrue(t.endswith("## Notas propias\nmío\n"))
        self.assertEqual(en.enlazar(d), 0)
        self.assertEqual(self.leer(ruta), t)

    def test_acuerdo_de_otra_institucion_es_solo_posible(self):
        d, ruta = self.armar("Acuerdo 224-2026.", {"Acuerdo 224-2026 (Gaceta 1)": ("Acuerdo", "224-2026",
                                                                                 "Secretaría de Salud")})
        en.enlazar(d)
        self.assertIn("Acuerdo 224-2026 → posible:", self.leer(ruta))

    def test_otro_acto_sin_numero_se_busca_por_titulo(self):
        d, ruta = self.armar("Acuerdo Ministerial SEN-119-2022.", {})
        with open(os.path.join(d, en.NORMATIVA, "Decretos", "2026", "Otros actos (Gaceta 36015).md"), "w",
                  encoding="utf-8") as f:
            f.write('---\ntipo_acto: "Otro acto"\nnumero: "No consta en la fuente"\n'
                    'titulo: "Según el sumario de La Gaceta: Acuerdo SEN-119-2022"\n'
                    'emisor: "SECRETARÍA DE ESTADO EN EL DESPACHO DE ENERGÍA"\ngaceta_fecha: "2022-08-30"\n---\n')
        en.enlazar(d)
        self.assertIn("SEN-119-2022 → [[Otros actos (Gaceta 36015)]]", self.leer(ruta))

    def test_sin_citas_no_toca(self):
        d, ruta = self.armar("Nada que citar.", {})
        antes = self.leer(ruta)
        en.enlazar(d)
        self.assertEqual(self.leer(ruta), antes)


if __name__ == "__main__":
    unittest.main()
