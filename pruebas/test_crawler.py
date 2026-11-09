"""Pruebas del crawler con HTML guardado del portal (sin conexión a internet).

ficha-1051.html y ficha-23.html son el bloque <main> de las fichas tal como las sirvió el portal el
9 de noviembre de 2026, con los espacios en blanco entre etiquetas compactados. Los listados son extractos
literales (selector de institución, dos tarjetas y paginación).
"""
import os
import shutil
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from crawler import notas as N  # noqa: E402
from crawler.extraer import Extraccion  # noqa: E402
from crawler.portal import (NO_CONSTA, URL_FICHA, BloqueoDelSitio, Respuesta, campos, consultar_comparador,  # noqa: E402
                            parsear_ficha, parsear_listado, url_listado)

sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "puente"))
import puente_tramites as P  # noqa: E402


def html(nombre):
    with open(os.path.join(AQUI, "html", nombre), encoding="utf-8") as f:
        return f.read()


TARJETA = """<article class="tramite-card diger-rrow" data-tramite-id="{id}">
<div class="diger-rrow__body">
<span class="diger-rrow__eyebrow">{inst}</span>
<h3 class="diger-rrow__title">{titulo}</h3>
</div>
<span class="diger-modbadge diger-modbadge--on">
<span class="diger-modbadge__dot" aria-hidden="true"></span>
{mod}
</span>
<a class="diger-rrow__cta" href="/api/landingPage/DetalleTramite/{id}"><span>Ver trámite</span></a>
</article>"""


def listado(tarjetas, instituciones=(("11076", "Instituto Hondureño de Transporte Terrestre"),)):
    opciones = "\n".join(f'<option value="{i}">{n}</option>' for i, n in instituciones)
    cuerpo = "\n".join(TARJETA.format(**t) for t in tarjetas)
    return (f'<main><select name="institutionFilter" id="institutionFilter"><option value="">Todas</option>{opciones}</select>'
            f'{cuerpo}<div class="pagination-modern"><a href="/tramites?page=1" class="page-btn active">1</a></div></main>')


COMPARADOR = {   # datos que devolvió el comparador del portal el 9 de noviembre de 2026
    1051: {"id": 1051, "tiempoEstimadoDias": 14, "nivelComplejidad": "Complejo", "scoreComplejidad": 12, "siglaInstitucion": "IHTT"},
    142: {"id": 142, "tiempoEstimadoDias": 13, "nivelComplejidad": "Complejo", "scoreComplejidad": 10, "siglaInstitucion": "SRECI"},
    705: {"id": 705, "tiempoEstimadoDias": 38, "nivelComplejidad": "Complejo", "scoreComplejidad": 35, "siglaInstitucion": "STSS"},
}


class ClienteFalso:
    def __init__(self, paginas, comparador=None):
        self.paginas = dict(paginas)
        self.comparador = COMPARADOR if comparador is None else comparador
        self.peticiones = 0
        self.consultas_comparador = []
        self.bloquear = False

    def enviar_json(self, url, ids):
        """Imita al portal: solo acepta entre 2 y 3 trámites y falla si alguno no existe."""
        self.consultas_comparador.append(list(ids))
        if not 2 <= len(ids) <= 3:
            return {"success": False, "message": "Debes seleccionar entre 2 y 3 trámites"}
        if any(i not in self.comparador for i in ids):
            return {"success": False, "message": "Algunos trámites no fueron encontrados"}
        return {"success": True, "tramites": [self.comparador[i] for i in ids]}

    def obtener(self, url, aceptar_404=True):
        self.peticiones += 1
        if self.bloquear:
            raise BloqueoDelSitio(url)
        if url in self.paginas:
            return Respuesta(200, url, self.paginas[url], {})
        if aceptar_404:
            return Respuesta(404, url, "", {})
        raise ConnectionError(url)

    def resolver_url_final(self, url):
        return (url, None)


class LecturaDeFichas(unittest.TestCase):
    def test_ficha_1051(self):
        f = parsear_ficha(html("ficha-1051.html"), 1051)
        self.assertEqual(f["titulo"], "Certificación de expediente en trámite")
        self.assertEqual(f["institucion"], "Instituto Hondureño de Transporte Terrestre")
        self.assertEqual(f["modalidad"], "En línea")
        self.assertEqual(f["numero"], "1051")
        self.assertEqual(f["etiquetas"], ["Aprobado"])
        self.assertEqual(f["accion"], {"texto": "Iniciar trámite en línea",
                                       "url": "https://sol.pdihonduras.gob.hn/IHTT/web/ciudadano/#/inicio"})
        self.assertEqual([p["etiqueta"] for p in f["pestanas"]],
                         ["Pasos del trámite", "Requisitos", "Lugares", "Entregables", "Más información"])
        pasos = f["pestanas"][0]["contenido"]["elementos"]
        self.assertEqual(len(pasos), 8)
        self.assertEqual([p["marca"] for p in pasos], [str(i) for i in range(1, 9)])
        self.assertTrue(pasos[0]["texto"][0].startswith('Crea tu Usuario: Si es tu primera vez'))
        req = f["pestanas"][1]["contenido"]["elementos"]
        self.assertEqual(req[1]["texto"], ["Recibo TGR-1 a favor del IHTT en la cuenta 12121"])
        lug = f["pestanas"][2]["contenido"]["lugares"][0]
        self.assertEqual([d["etiqueta"] for d in lug["datos"]], ["Ciudad", "Dirección", "Teléfonos"])
        self.assertEqual(lug["datos"][2]["valor"], ["9999-3080"])
        tabla = f["pestanas"][4]["contenido"]
        self.assertEqual(tabla["encabezados"], ["Tipo de enlace", "URL", "Acción"])
        self.assertEqual([x["celdas"][0] for x in tabla["filas"]], ["Trámite en línea", "Aplicación", "Informativo"])
        c = campos(f)
        self.assertEqual(c["responsable"], "Secretario General")
        self.assertEqual(c["dirigido_a"], ["Personas naturales y jurídicas"])
        self.assertEqual(c["costo"], NO_CONSTA)
        self.assertEqual(c["tiempo_respuesta"], NO_CONSTA)
        self.assertIsNone(c["marco_legal"])
        self.assertEqual(c["actualizado_portal"], NO_CONSTA)

    def test_ficha_23_presencial_con_documento_y_dependencia(self):
        f = parsear_ficha(html("ficha-23.html"), 23)
        self.assertEqual(f["titulo"], "Solicitud de Préstamo de Consumo")
        self.assertEqual(f["modalidad"], "Presencial")
        self.assertIsNone(f["accion"])
        paso4 = f["pestanas"][0]["contenido"]["elementos"][3]
        self.assertEqual(paso4["meta"], [{"etiqueta": "Dependencia", "valor": ["Gerencia de Préstamos"]}])
        req1 = f["pestanas"][1]["contenido"]["elementos"][0]
        self.assertEqual(req1["meta"], [{"etiqueta": "Documento", "valor": ["638398781356648008.pdf"]}])
        self.assertEqual(req1["documentos"],
                         ["https://beta.sigpret.gob.hn/Content/Uploads/Tramites/Requisitos/638398781356648008.pdf"])
        c = campos(f)
        self.assertEqual(c["dirigido_a"], ["Activos , jubilados , pensionados."])   # tal cual, sin corregir
        self.assertEqual(c["url_inicio"], NO_CONSTA)

    def test_el_html_compactado_equivale_al_crudo(self):
        compacto = html("ficha-1051.html")
        crudo = compacto.replace("\n<", "\n\t\t\t\t<").replace(">\n", ">\n\t\t\t")
        self.assertEqual(parsear_ficha(compacto, 1051), parsear_ficha(crudo, 1051))

    def test_pagina_que_no_es_ficha(self):
        from crawler.portal import FichaInvalida
        with self.assertRaises(FichaInvalida):
            parsear_ficha("<html><main><p>Error</p></main></html>", 5)

    def test_listados(self):
        d = parsear_listado(html("listado-11060-extracto.html"))
        self.assertEqual(d["instituciones"][0], ("11054", "Secretaría de Salud"))
        self.assertIn(("11060", "Secretaría de Trabajo y Seguridad Social"), d["instituciones"])
        self.assertEqual([t["id"] for t in d["tramites"]], [705, 712])
        self.assertEqual(d["tramites"][0]["modalidad"], "En línea")
        self.assertEqual(d["paginas"], 1)
        self.assertEqual(parsear_listado(html("listado-paginas-extracto.html"))["paginas"], 25)


class Notas(unittest.TestCase):
    def test_nota_1051(self):
        f = parsear_ficha(html("ficha-1051.html"), 1051)
        enl = N.enlace("10 Trámites del Estado/Instituto Hondureño de Transporte Terrestre",
                       "Instituto Hondureño de Transporte Terrestre", "Instituto Hondureño de Transporte Terrestre")
        comp = {"tiempo_estimado_dias": 14, "nivel_complejidad": "Complejo", "puntaje_complejidad": 12, "siglas_institucion": "IHTT"}
        t = N.render_tramite(f, enl, "2026-11-09T13:05", "https://sol.pdihonduras.gob.hn/IHTT/web/ciudadano/#/inicio", None, comp)
        fm, cuerpo = P.separar(t)
        claves = [c for c, _ in P.bloques(fm)]
        self.assertEqual(claves, [k for k in N.PROPIEDADES_TRAMITE if k != "no_aparece_desde"])
        self.assertIn("comparador_tiempo_dias: 14", t)
        self.assertIn('comparador_complejidad: "Complejo"', t)
        self.assertIn("- Tiempo estimado: 14 días", t)
        self.assertIn('tiempo_respuesta: "No consta en el portal"', t)      # el comparador no sustituye a la ficha
        sin = N.render_tramite(f, enl, "2026-11-09T13:05", None, "sin red", None, "sin red")
        self.assertNotIn("comparador_tiempo_dias", sin)
        self.assertIn("No se pudo consultar el comparador en la extracción.", sin)
        self.assertLess(cuerpo.index(N.INICIO), cuerpo.index(N.FIN))
        self.assertLess(cuerpo.index(N.FIN), cuerpo.index(N.NOTAS_PROPIAS))
        self.assertIn('institucion: "[[10 Trámites del Estado/Instituto Hondureño de Transporte Terrestre/'
                      'Instituto Hondureño de Transporte Terrestre|Instituto Hondureño de Transporte Terrestre]]"', t)
        self.assertIn("1. Crea tu Usuario", t)
        self.assertIn("- Horario: No consta en el portal", t)
        self.assertIn("- Marco legal: No consta en el portal", t)
        self.assertEqual(N.nombre_nota_tramite(1051, f["titulo"]), "TR-1051 Certificación de expediente en trámite")

    def test_nombres_y_escapes(self):
        self.assertEqual(N.limpiar_nombre('TR-1 A/B: ¿C? [x] #1 | "y"'), "TR-1 A B ¿C x 1 y")
        self.assertEqual(N.md("Ver #etiqueta y [[enlace]] con <b>"), "Ver \\#etiqueta y \\[\\[enlace\\]\\] con \\<b>")
        self.assertEqual(N.md("https://sitio.hn/#/inicio"), "https://sitio.hn/#/inicio")
        self.assertEqual(N.celda("a | b"), "a \\| b")

    def test_listas_de_propiedades_iguales_en_crawler_y_puente(self):
        self.assertEqual(N.PROPIEDADES_TRAMITE, P.PROPIEDADES_TRAMITE)
        self.assertEqual(N.PROPIEDADES_INSTITUCION, P.PROPIEDADES_INSTITUCION)


class Corridas(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.f1051 = html("ficha-1051.html")
        self.f23 = html("ficha-23.html")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def paginas(self, ids, f23=None):
        tarjetas = []
        if 1051 in ids:
            tarjetas.append({"id": 1051, "inst": "Instituto Hondureño de Transporte Terrestre", "titulo": "x", "mod": "En línea"})
        if 23 in ids:
            tarjetas.append({"id": 23, "inst": "Instituto de Previsión Social de los Empleados de la Universidad Nacional Autónoma de Honduras",
                             "titulo": "y", "mod": "Presencial"})
        return {url_listado(1): listado(tarjetas), URL_FICHA.format(id=1051): self.f1051,
                URL_FICHA.format(id=23): f23 or self.f23}

    def leer(self, rel):
        with open(os.path.join(self.dir, rel), encoding="utf-8") as f:
            return f.read()

    def test_piloto_crea_notas_y_no_reescribe_sin_cambios(self):
        c = ClienteFalso(self.paginas([1051, 23]))
        ex = Extraccion(self.dir, c, "piloto", [], [1051, 142, 23])   # 142 sin HTML guardado: queda como error
        self.assertEqual(ex.ejecutar(), 0)
        self.assertEqual([e["donde"] for e in ex.r["errores"]], [URL_FICHA.format(id=142)])
        self.assertEqual(len(ex.r["nuevos"]), 2)
        nota = "10 Trámites del Estado/Instituto Hondureño de Transporte Terrestre/TR-1051 Certificación de expediente en trámite.md"
        self.assertIn("id_portal: 1051", self.leer(nota))
        inst = "10 Trámites del Estado/Instituto Hondureño de Transporte Terrestre/Instituto Hondureño de Transporte Terrestre.md"
        self.assertIn("id_portal_institucion: 11076", self.leer(inst))
        self.assertIn('siglas_comparador: "IHTT"', self.leer(inst))
        self.assertIn("comparador_tiempo_dias: 14", self.leer(nota))
        self.assertIn("No se pudo consultar el comparador", self.leer(
            "10 Trámites del Estado/Instituto de Previsión Social de los Empleados de la Universidad Nacional Autónoma de Honduras/"
            "TR-23 Solicitud de Préstamo de Consumo.md"))
        self.assertIn("[[TR-1051 Certificación de expediente en trámite|Certificación de expediente en trámite]]", self.leer(inst))
        for rel in ("Índice de trámites.md", "Trámites.base", "_Sistema/Última extracción.md", "_Sistema/Registro de cambios.md"):
            self.assertTrue(os.path.exists(os.path.join(self.dir, "10 Trámites del Estado", rel)), rel)
        mtime = os.path.getmtime(os.path.join(self.dir, nota))
        ex2 = Extraccion(self.dir, ClienteFalso(self.paginas([1051, 23])), "piloto", [], [1051, 142, 23])
        ex2.ejecutar()
        self.assertEqual(ex2.r["sin_cambios"], 2)
        self.assertEqual(ex2.r["nuevos"] + ex2.r["modificados"], [])
        self.assertEqual(os.path.getmtime(os.path.join(self.dir, nota)), mtime)
        self.assertIn("Sin cambios en las fichas.", self.leer("10 Trámites del Estado/_Sistema/Registro de cambios.md"))

    def test_comparador_agrupa_de_a_tres_y_rescata_los_sueltos(self):
        c = ClienteFalso({})
        datos, errores = consultar_comparador(c, [705, 1051, 23, 142])
        self.assertEqual(sorted(datos), [142, 705, 1051])
        self.assertEqual(datos[1051]["tiempo_estimado_dias"], 14)
        self.assertEqual(list(errores), [23])
        self.assertTrue(all(2 <= len(g) <= 3 for g in c.consultas_comparador))

    def test_si_el_comparador_falla_se_conserva_el_dato_anterior(self):
        Extraccion(self.dir, ClienteFalso(self.paginas([1051])), "piloto", [], [1051, 142]).ejecutar()
        ex = Extraccion(self.dir, ClienteFalso(self.paginas([1051]), comparador={}), "piloto", [], [1051, 142])
        ex.ejecutar()
        self.assertEqual(ex.r["modificados"], [])
        self.assertEqual(ex.estado["tramites"]["1051"]["comparador"]["tiempo_estimado_dias"], 14)

    def test_cambio_en_requisitos_queda_en_el_registro(self):
        Extraccion(self.dir, ClienteFalso(self.paginas([23])), "piloto", [], [23]).ejecutar()
        cambiada = self.f23.replace("Constancia de Trabajo con copia adjunta", "Constancia de Trabajo original")
        ex = Extraccion(self.dir, ClienteFalso(self.paginas([23], cambiada)), "piloto", [], [23])
        ex.ejecutar()
        self.assertEqual(ex.r["modificados"][0]["secciones"], ["Requisitos"])
        reg = self.leer("10 Trámites del Estado/_Sistema/Registro de cambios.md")
        self.assertIn("Modificado: TR-23 Solicitud de Préstamo de Consumo · Requisitos", reg)
        self.assertLess(reg.index("Modificado"), reg.index("Nuevo"))   # lo más reciente arriba

    def test_completo_marca_desaparecidos_sin_borrar(self):
        Extraccion(self.dir, ClienteFalso(self.paginas([1051, 23])), "completo").ejecutar()
        ex = Extraccion(self.dir, ClienteFalso(self.paginas([1051])), "completo")
        ex.ejecutar()
        self.assertEqual([x["id"] for x in ex.r["desaparecidos"]], [23])
        rel = ex.estado["tramites"]["23"]["archivo"]
        t = self.leer(rel)
        self.assertIn('estado_portal: "Ya no aparece en el portal"', t)
        self.assertIn(f"no_aparece_desde: {ex.hoy}", t)
        self.assertIn("1. Realizar cita en el sistema", t)    # se conserva el contenido
        ex3 = Extraccion(self.dir, ClienteFalso(self.paginas([1051, 23])), "completo")
        ex3.ejecutar()
        self.assertEqual([x["id"] for x in ex3.r["reaparecidos"]], [23])
        self.assertIn('estado_portal: "Vigente"', self.leer(rel))

    def test_listado_vacio_no_marca_nada(self):
        Extraccion(self.dir, ClienteFalso(self.paginas([1051, 23])), "completo").ejecutar()
        ex = Extraccion(self.dir, ClienteFalso(self.paginas([])), "completo")
        ex.ejecutar()
        self.assertEqual(ex.r["desaparecidos"], [])
        self.assertTrue(any("No se marcó" in a for a in ex.r["avisos"]))

    def test_bloqueo_detiene_sin_tocar_fichas(self):
        Extraccion(self.dir, ClienteFalso(self.paginas([1051])), "piloto", [], [1051]).ejecutar()
        c = ClienteFalso({})
        c.bloquear = True
        ex = Extraccion(self.dir, c, "piloto", [], [1051])
        self.assertEqual(ex.ejecutar(), 2)
        self.assertIn("La corrida se detuvo", self.leer("10 Trámites del Estado/_Sistema/Última extracción.md"))
        self.assertIn('estado_portal: "Vigente"', self.leer(ex.estado["tramites"]["1051"]["archivo"]))


if __name__ == "__main__":
    unittest.main()
