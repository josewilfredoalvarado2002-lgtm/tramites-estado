"""Pruebas de la limpieza y separación por acto con el texto real guardado por la sonda."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gaceta import texto as T

SONDA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gaceta_sonda")


def cargar(carpeta):
    d = os.path.join(SONDA, carpeta)
    with open(os.path.join(d, "info.json"), encoding="utf-8") as f:
        ed = json.load(f)["edicion"]
    with open(os.path.join(d, "pymupdf_columnas.txt"), encoding="utf-8") as f:
        pags = re.split(r"\n===== Página \d+ =====\n", f.read())[1:]
    reng, res = T.limpiar_paginas(pags)
    return ed, reng, res, T.separar_actos(reng, ed["sumario"])


@unittest.skipUnless(os.path.isdir(os.path.join(SONDA, "20261002_37261")), "sin datos de la sonda")
class Gaceta(unittest.TestCase):
    def test_octubre_2026_coincide_con_el_sumario(self):
        ed, reng, res, actos = cargar("20261002_37261")
        self.assertEqual((res["paginas_a"], res["paginas_b"]), (48, 20))
        self.assertEqual([(a["tipo"], a["numero"], a["paginas"]) for a in actos],
                         [("Acuerdo", "047-DP-2026", "A. 1 - 3"), ("Acuerdo", "053-DP-2026", "A. 3 - 30"),
                          ("Decreto", "196-2026", "A. 30 - 34"), ("Certificación", "", "A. 35 - 48")])
        self.assertEqual(actos[0]["emisor"], "Poder Ejecutivo")
        self.assertEqual(actos[3]["emisor"], "Instituto Nacional de Migración INM")

    def test_sin_encabezados_de_pagina_ni_sumario(self):
        for carpeta in sorted(os.listdir(SONDA)):
            if not carpeta[:1].isdigit():
                continue
            _, reng, _, actos = cargar(carpeta)
            todo = "\n".join(p for a in actos for p in a["parrafos"])
            for malo in ("Acuerdos y Leyes", "Avisos Legales", "Desprendible para su comodidad",
                         "REPÚBLICA DE HONDURAS - TEGUCIGALPA", "DECANO DE LA PRENSA"):
                self.assertNotIn(malo, todo, f"{carpeta}: quedó '{malo}'")
            self.assertFalse(any(x in ("A.", "B.", "La Gaceta") for _, x in reng), carpeta)

    def test_parrafos_corridos(self):
        _, _, _, actos = cargar("20261002_37261")
        p = actos[0]["parrafos"]
        self.assertTrue(p[1].startswith("CONSIDERANDO: Que de conformidad") and p[1].endswith("conforme a ley."))
        self.assertTrue(p[2].endswith("él les confíe."))  # párrafo cortado por el sumario y por la columna
        self.assertTrue(any(x.startswith("4. Preparar y/o aprobar") for x in p))

    def test_otras_epocas(self):
        self.assertEqual(len(cargar("20110103_32406")[3]), 21)
        a = cargar("20230102_36118")[3]
        self.assertEqual([(x["tipo"], x["numero"]) for x in a], [("Resolución", "1097-2022")])
        a = cargar("20180102_34531")[3]  # el encabezado no viene en el texto: se rotula con el sumario
        self.assertEqual((a[0]["numero"], a[0]["titulo"]), ("PCM-078-2017", ""))
        self.assertIn("Según el sumario de La Gaceta", T.nota_acto(cargar("20180102_34531")[0], a[0], "2026-11-09"))

    def test_nota_con_marcadores(self):
        ed, _, res, actos = cargar("20261005_37262")
        n = T.nota_acto(ed, actos[0], "2026-11-09")
        self.assertIn(T.INICIO, n)
        self.assertTrue(n.rstrip().endswith("## Notas propias"))
        self.assertIn("#### Artículo 1", n)
        usadas = set()
        rutas = [T.ruta_acto(ed, a, usadas) for a in actos]
        self.assertEqual(rutas[0], "11 Normativa/Decretos/2026/Decreto 176-2026 (Gaceta 37262).md")
        self.assertIn(rutas[0][:-3], T.nota_edicion(ed, actos, rutas, res, "2026-11-09"))


if __name__ == "__main__":
    unittest.main()
