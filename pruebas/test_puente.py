"""Pruebas del puente entre el repositorio y la bóveda (carpetas temporales, sin git)."""
import os
import shutil
import sys
import tempfile
import time
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "puente"))
import puente_tramites as P  # noqa: E402

NOTA_REPO = """---
tipo: "tramite"
id_portal: 1051
titulo: "Título nuevo"
aliases:
  - "Título nuevo"
huella: "nueva"
estado_portal: "Vigente"
---
<!-- portal:inicio -->
# Título nuevo
Requisitos nuevos
<!-- portal:fin -->

## Notas propias
"""

NOTA_BOVEDA = """---
tipo: "tramite"
id_portal: 1051
titulo: "Título viejo"
aliases:
  - "Título viejo"
huella: "vieja"
estado_portal: "Ya no aparece en el portal"
no_aparece_desde: 2026-12-01
mi_etiqueta: importante
tags:
  - consulta
---
<!-- portal:inicio -->
# Título viejo
Requisitos viejos
<!-- portal:fin -->

## Notas propias

Lo usé en el caso [[CD-2026-001]]. No se debe perder.
"""


class Fusion(unittest.TestCase):
    def test_reemplaza_solo_lo_del_portal(self):
        r = P.fusionar(NOTA_REPO, NOTA_BOVEDA)
        self.assertIn("Requisitos nuevos", r)
        self.assertNotIn("Requisitos viejos", r)
        self.assertIn('titulo: "Título nuevo"', r)
        self.assertIn("mi_etiqueta: importante", r)
        self.assertIn("tags:\n  - consulta", r)
        self.assertNotIn("no_aparece_desde", r)          # propiedad del portal que ya no corresponde
        self.assertIn("Lo usé en el caso [[CD-2026-001]]. No se debe perder.", r)
        self.assertTrue(r.startswith("---\ntipo:"))

    def test_sin_marcadores_no_se_toca(self):
        self.assertIsNone(P.fusionar(NOTA_REPO, NOTA_BOVEDA.replace("<!-- portal:fin -->", "")))


class Sincronizacion(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.repo = os.path.join(self.base, "repo")
        self.boveda = os.path.join(self.base, "boveda")
        os.makedirs(os.path.join(self.repo, P.CARPETA, "IHTT"))
        os.makedirs(os.path.join(self.boveda, ".casedeck"))
        os.makedirs(os.path.join(self.boveda, "01 Casos"))
        self.rel = os.path.join(P.CARPETA, "IHTT", "TR-1051 X.md")
        self.escribir(self.repo, self.rel, NOTA_REPO)
        self.escribir(self.repo, os.path.join(P.CARPETA, "Trámites.base"), "filters: x\n")
        self.escribir(self.repo, os.path.join(P.CARPETA, "IHTT", "imagen.png"), "no se copia")
        self.estado = {}

    def tearDown(self):
        shutil.rmtree(self.base)

    def escribir(self, raiz, rel, texto, hace=None):
        ruta = os.path.join(raiz, rel)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        if hace:
            t = time.time() - hace
            os.utime(ruta, (t, t))

    def leer(self, raiz, rel):
        with open(os.path.join(raiz, rel), encoding="utf-8") as f:
            return f.read()

    def test_copia_nuevas_y_luego_no_hace_nada(self):
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual(r["nuevas"], 2)
        self.assertEqual(self.leer(self.boveda, self.rel), NOTA_REPO)
        self.assertFalse(os.path.exists(os.path.join(self.boveda, P.CARPETA, "IHTT", "imagen.png")))
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual((r["nuevas"], r["actualizadas"], r["iguales"]), (0, 0, 2))

    def test_actualiza_respetando_notas_propias(self):
        self.escribir(self.boveda, self.rel, NOTA_BOVEDA, hace=3600)
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual(r["actualizadas"], 1)
        t = self.leer(self.boveda, self.rel)
        self.assertIn("Requisitos nuevos", t)
        self.assertIn("No se debe perder.", t)
        self.assertIn("mi_etiqueta: importante", t)

    def test_nota_en_edicion_se_deja_para_la_siguiente(self):
        self.escribir(self.boveda, self.rel, NOTA_BOVEDA)   # recién modificada
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual(r["en_edicion"], 1)
        self.assertIn("Requisitos viejos", self.leer(self.boveda, self.rel))
        self.assertNotIn(P.CARPETA + "/IHTT/TR-1051 X.md", self.estado)

    def test_lo_que_escribio_el_puente_no_cuenta_como_edicion(self):
        P.sincronizar(self.repo, self.boveda, self.estado)          # el puente acaba de escribir la nota
        self.escribir(self.repo, self.rel, NOTA_REPO.replace("Requisitos nuevos", "Requisitos de diciembre"))
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual((r["actualizadas"], r["en_edicion"]), (1, 0))
        self.assertIn("Requisitos de diciembre", self.leer(self.boveda, self.rel))

    def test_nunca_borra(self):
        P.sincronizar(self.repo, self.boveda, self.estado)
        os.remove(os.path.join(self.repo, self.rel))
        P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertTrue(os.path.exists(os.path.join(self.boveda, self.rel)))

    def test_no_escribe_fuera_de_la_carpeta_10(self):
        afuera = os.path.join(self.base, "afuera")
        os.makedirs(afuera)
        os.makedirs(os.path.join(self.boveda, P.CARPETA))
        os.symlink(afuera, os.path.join(self.boveda, P.CARPETA, "IHTT"))
        r = P.sincronizar(self.repo, self.boveda, self.estado)
        self.assertEqual(os.listdir(afuera), [])
        self.assertIn(os.path.join("IHTT", "TR-1051 X.md"), r["rechazadas"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.boveda, "01 Casos"))), [])

    def test_copia_tambien_normativa(self):
        rel = os.path.join("11 Normativa", "Decretos", "2026", "Decreto 1-2026 (Gaceta 1).md")
        self.escribir(self.repo, rel, "---\ntipo: \"norma\"\ngaceta_fecha: \"2026-03-05\"\nhuella: \"a\"\n---\n" + P.INICIO + "\nuno\n" + P.FIN + "\n\n## Notas propias\n\n")
        P.sincronizar(self.repo, self.boveda, self.estado, carpeta="11 Normativa")
        # en la bóveda el acto queda por año, tipo y mes de publicación
        destino = os.path.join(self.boveda, "11 Normativa", "02 Instrumentos normativos", "2026", "02 Decretos", "2026-03 Marzo",
                               "Decreto 1-2026 (Gaceta 1).md")
        self.assertFalse(os.path.exists(os.path.join(self.boveda, rel)))
        with open(destino, encoding="utf-8") as f:
            texto = f.read()
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto.replace("---\n" + P.INICIO, "mia: si\n---\n" + P.INICIO) + "apunte mío\n")
        self.escribir(self.repo, rel, "---\ntipo: \"norma\"\ngaceta_fecha: \"2026-03-05\"\nhuella: \"b\"\n---\n" + P.INICIO + "\ndos\n" + P.FIN + "\n\n## Notas propias\n\n")
        P.sincronizar(self.repo, self.boveda, self.estado, carpeta="11 Normativa", ahora=time.time() + 3600)
        with open(destino, encoding="utf-8") as f:
            final = f.read()
        for trozo in ('huella: "b"', "mia: si", "\ndos\n", "apunte mío"):
            self.assertIn(trozo, final)
        self.assertNotIn("\nuno\n", final)
        self.assertIn("11 Normativa/Decretos/2026/Decreto 1-2026 (Gaceta 1).md", self.estado)

    def test_acto_reemplazado_se_archiva_sin_borrar(self):
        cab = "---\ntipo: \"norma\"\ngaceta_fecha: \"2022-08-30\"\nhuella: \"a\"\n---\n" + P.INICIO + "\nx\n" + P.FIN + "\n\n## Notas propias\n\n"
        viejo = os.path.join("11 Normativa", "Otros actos", "2022", "Otros actos (Gaceta 5).md")
        nuevo = os.path.join("11 Normativa", "Acuerdos", "2022", "Acuerdo SEN-119-2022 (Gaceta 5).md")
        self.escribir(self.repo, viejo, cab)
        P.sincronizar(self.repo, self.boveda, self.estado, carpeta="11 Normativa")
        en_boveda = os.path.join(self.boveda, "11 Normativa", "02 Instrumentos normativos", "2022", "99 Otros actos",
                                 "2022-08 Agosto", "Otros actos (Gaceta 5).md")
        tipos = P.TIPOS_NORMA["Otros actos"]
        en_boveda = en_boveda.replace("99 Otros actos", tipos)
        with open(en_boveda, "a", encoding="utf-8") as f:
            f.write("mi apunte\n")
        os.utime(en_boveda, (time.time() - 3600, time.time() - 3600))
        os.remove(os.path.join(self.repo, viejo))
        self.escribir(self.repo, nuevo, cab)
        P.sincronizar(self.repo, self.boveda, self.estado, carpeta="11 Normativa")
        movidas, con_notas = P.archivar_reemplazadas(self.repo, self.boveda, minimo_repo=1)
        self.assertEqual(movidas, 1)
        self.assertEqual(len(con_notas), 1)
        self.assertFalse(os.path.exists(en_boveda))
        archivada = os.path.join(self.boveda, P.ARCHIVO_REEMPLAZADAS, "02 Instrumentos normativos", "2022", tipos,
                                 "2022-08 Agosto", "Otros actos (Gaceta 5).md")
        with open(archivada, encoding="utf-8") as f:
            self.assertIn("mi apunte", f.read())
        self.assertEqual(P.archivar_reemplazadas(self.repo, self.boveda, minimo_repo=1)[0], 0)

    def test_repositorio_incompleto_no_archiva(self):
        self.assertEqual(P.archivar_reemplazadas(self.repo, self.boveda), (0, []))

    def test_normativa_traduce_rutas_enlaces_e_indices(self):
        ed = os.path.join("11 Normativa", "La Gaceta", "2026", "La Gaceta 7 (2026-03-05).md")
        acto = os.path.join("11 Normativa", "Acuerdos", "2026", "Acuerdo 9-2025 (Gaceta 7).md")
        self.escribir(self.repo, ed, "---\ntipo: \"gaceta\"\n---\n" + P.INICIO + "\n- [[11 Normativa/Acuerdos/2026/Acuerdo 9-2025 (Gaceta 7)|ACUERDO 9]]\n" + P.FIN + "\n")
        self.escribir(self.repo, acto, "---\ntipo: \"norma\"\ntitulo: \"ACUERDO No. 9-2025\"\ngaceta_fecha: \"2026-03-05\"\n"
                      "gaceta: \"[[11 Normativa/La Gaceta/2026/La Gaceta 7 (2026-03-05)|La Gaceta 7]]\"\n---\n" + P.INICIO +
                      "\n| Publicado en | [[11 Normativa/La Gaceta/2026/La Gaceta 7 (2026-03-05)\\|La Gaceta 7]] |\n" + P.FIN + "\n")
        self.escribir(self.repo, os.path.join("11 Normativa", "Índice de normativa.md"), "---\ntipo: x\n---\nrepo\n")
        P.sincronizar(self.repo, self.boveda, self.estado, carpeta="11 Normativa")
        base = os.path.join(self.boveda, "11 Normativa")
        nuevo_acto = os.path.join(base, "02 Instrumentos normativos", "2026", "01 Acuerdos", "2026-03 Marzo", "Acuerdo 9-2025 (Gaceta 7).md")
        nueva_ed = os.path.join(base, "01 Fuente oficial", "La Gaceta", "2026", "La Gaceta 7 (2026-03-05).md")
        with open(nuevo_acto, encoding="utf-8") as f:
            texto = f.read()
        self.assertEqual(texto.count("[[11 Normativa/01 Fuente oficial/La Gaceta/2026/La Gaceta 7 (2026-03-05)"), 2)
        self.assertIn("\\|La Gaceta 7]]", texto)
        with open(nueva_ed, encoding="utf-8") as f:
            self.assertIn("[[11 Normativa/02 Instrumentos normativos/2026/01 Acuerdos/2026-03 Marzo/Acuerdo 9-2025 (Gaceta 7)|ACUERDO 9]]", f.read())
        for vieja in ("Acuerdos", "La Gaceta", "Índice de normativa.md"):
            self.assertFalse(os.path.exists(os.path.join(base, vieja)))
        self.assertGreater(P.indices_normativa(self.boveda), 0)
        self.assertEqual(P.indices_normativa(self.boveda), 0)
        with open(os.path.join(base, "02 Instrumentos normativos", "2026", "01 Acuerdos", "2026-03 Marzo.md"), encoding="utf-8") as f:
            self.assertIn("|ACUERDO No. 9-2025]]", f.read())
        with open(os.path.join(base, "Índice de normativa.md"), encoding="utf-8") as f:
            indice = f.read()
        self.assertIn("Normativa 2026]]", indice)
        self.assertEqual(indice.count("[[10 Trámites del Estado/"), 1)
        self.assertNotIn("[[00 Panel", indice)

    def test_equivalencias_solo_proponen(self):
        carpeta = os.path.join(P.CARPETA, "Instituto Hondureño de Transporte Terrestre")
        self.escribir(self.boveda, os.path.join(carpeta, "Instituto Hondureño de Transporte Terrestre.md"),
                      '---\ntipo: "institucion_portal"\nnombre: "Instituto Hondureño de Transporte Terrestre"\nsiglas_comparador: "IHTT"\n---\n')
        cat = os.path.join("20 Despacho/Catálogos", "Instituciones")
        self.escribir(self.boveda, os.path.join(cat, "Instituto Hondureño de Transporte Terrestre.md"), "---\ntipo: institucion\n---\n")
        self.escribir(self.boveda, os.path.join(cat, "Transporte (IHTT).md"), "---\ntipo: institucion\nsiglas: IHTT\n---\n")
        self.escribir(self.boveda, os.path.join(cat, "Secretaría de Finanzas.md"), "---\ntipo: institucion\n---\n")
        t = P.equivalencias(self.boveda)
        fila = [x for x in t.split("\n") if x.startswith("| Instituto Hondureño")][0]
        self.assertIn("[[20 Despacho/Catálogos/Instituciones/Instituto Hondureño de Transporte Terrestre\\|Instituto Hondureño de Transporte Terrestre]] (mismo nombre)", fila)
        self.assertIn("[[20 Despacho/Catálogos/Instituciones/Transporte (IHTT)\\|Transporte (IHTT)]]", fila)
        self.assertNotIn("Finanzas", fila)
        self.assertTrue(fila.endswith("| Pendiente |"))


if __name__ == "__main__":
    unittest.main()
