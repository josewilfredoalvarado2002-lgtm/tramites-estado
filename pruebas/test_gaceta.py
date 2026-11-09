"""Pruebas del índice de La Gaceta con un extracto del HTML de enag.gob.hn (sin conexión)."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from gaceta.listado import parsear_ediciones, tamano_mb, url_mes  # noqa: E402


class IndiceDeLaGaceta(unittest.TestCase):
    def test_edicion(self):
        with open(os.path.join(AQUI, "html", "gaceta-listado-extracto.html"), encoding="utf-8") as f:
            d = parsear_ediciones(f.read())
        self.assertEqual(len(d["ediciones"]), 1)
        e = d["ediciones"][0]
        self.assertEqual((e["fecha"], e["numero"]), ("2026-10-01", 37260))
        self.assertEqual(e["descarga"], "https://enag.gob.hn/index.php/gaceta-digital/20261001-37260/download")
        self.assertEqual(e["tamano"], "3.42 MB")
        self.assertEqual(e["fecha_creacion"], "01-10-2026")
        self.assertEqual(e["sumario"][0], "PODER EJECUTIVO")
        self.assertIn("Sección B", e["sumario"][-1])
        self.assertEqual(d["siguientes"], [5, 10])

    def test_utilidades(self):
        self.assertEqual(tamano_mb("3.42 MB"), 3.42)
        self.assertGreater(tamano_mb("1.16 GB"), 1000)
        self.assertEqual(url_mes(2026, "octubre", 5), "https://enag.gob.hn/index.php/gaceta-digital/2026/octubre?start=5")


if __name__ == "__main__":
    unittest.main()
