import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gaceta import reparar as R  # noqa: E402


class Reparar(unittest.TestCase):
    def test_sumario_pegado(self):
        self.assertEqual(R.sumario("SECRETARÍA DE ESTADO EN EL DESPACHO DE FINANZASAcuerdo Número 372-2025"),
                         "SECRETARÍA DE ESTADO EN EL DESPACHO DE FINANZAS: Acuerdo Número 372-2025")
        self.assertEqual(R.sumario("Acuerdo DCHA-052-2025CONSEJO NACIONAL"), "Acuerdo DCHA-052-2025; CONSEJO NACIONAL")
        self.assertEqual(R.sumario("Acuerdo SEN-119-2022"), "Acuerdo SEN-119-2022")
        self.assertEqual(R.sumario("Decreto PCM-05-2020 y ONGs"), "Decreto PCM-05-2020 y ONGs")

    def test_numeros_cortados(self):
        self.assertEqual(R.linea("Decreto Legislativo No. 170- 2016, a partir"), "Decreto Legislativo No. 170-2016, a partir")
        self.assertEqual(R.linea("Acuerdo Ejecutivo No. SAG- 125-2022 y"), "Acuerdo Ejecutivo No. SAG-125-2022 y")
        self.assertEqual(R.linea("PCM-016- 2020 del 3"), "PCM-016-2020 del 3")
        self.assertEqual(R.linea("del 1 al 5 - 2 días"), "del 1 al 5 - 2 días")

    def test_guiones_solo_si_la_forma_existe(self):
        voc = {"subsector", "sector", "técnica-administrativa", "técnicaadministrativa", "administrativa",
               "carnetizada"}
        self.assertEqual(R.linea("el sub- sector y la parte técnica- administrativa", voc),
                         "el subsector y la parte técnica-administrativa")
        self.assertEqual(R.linea("carne- tizada", voc), "carnetizada")
        self.assertEqual(R.linea("el petróleo- ya refinado", voc), "el petróleo- ya refinado")

    def test_parrafos_partidos(self):
        md = ("CONSIDERANDO: Que mediante Acuerdo Ejecutivo No.\n\n043-2020 de fecha 01 de octubre\n\n"
              "que se extiende por la columna\n\na) primer inciso\n\n#### Artículo 1\n\nARTÍCULO 1.- Texto.")
        self.assertEqual(R.texto(md), "CONSIDERANDO: Que mediante Acuerdo Ejecutivo No. 043-2020 de fecha 01 de octubre "
                         "que se extiende por la columna\n\na) primer inciso\n\n#### Artículo 1\n\nARTÍCULO 1.- Texto.")

    def test_letras_separadas(self):
        voc = {"de": 900, "la": 800, "república": 50, "decreta": 30, "ces": 3, "os": 2, "migratorios": 4}
        self.assertEqual(R.linea("D E L A R E P Ú B L I C A D E HONDURAS", voc), "DE LA REPÚBLICA DE HONDURAS")
        self.assertEqual(R.linea("D E C R E T A :", voc), "DECRETA:")
        self.assertEqual(R.linea("c e s o s m i g r a t o r i o s", voc), "c e s o s m i g r a t o r i o s")

    def test_espacios(self):
        self.assertEqual(R.linea("dice  esto , y aquello ;"), "dice esto, y aquello;")
        self.assertEqual(R.linea("Decreto No.83- 2004 a las 10 : 30"), "Decreto No. 83-2004 a las 10 : 30")

    def test_nota_completa_actualiza_huella_y_es_idempotente(self):
        nota = ('---\ntipo: "norma"\ntitulo: "Según el sumario de La Gaceta: FINANZASAcuerdo 5"\nhuella: "x"\n---\n'
                '<!-- portal:inicio -->\n# Según el sumario de La Gaceta: FINANZASAcuerdo 5\n\n## Texto\n\n'
                'Decreto No. 170- 2016.\n\n## Fuente\n\nf\n')
        una = R.reparar_nota(nota, frozenset())
        self.assertIn("FINANZAS: Acuerdo 5", una)
        self.assertIn("170-2016", una)
        self.assertNotIn('huella: "x"', una)
        self.assertEqual(R.reparar_nota(una, frozenset()), una)


if __name__ == "__main__":
    unittest.main()
