"""Extracción del Portal de Trámites del Estado de Honduras.

Modos:
  sonda     Prueba si el portal responde desde donde corre (por ejemplo, GitHub Actions).
            Pide el listado y la ficha 1051, guarda el HTML crudo en pruebas/html/crudo y no escribe notas.
  piloto    Institución 11060 y fichas 142 y 1051 (se pueden cambiar con --instituciones y --fichas).
  completo  Catálogo completo desde el listado general del portal.

Uso:  python3 -m crawler.extraer --modo piloto
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import unicodedata

from . import notas as N
from .portal import (URL_FICHA, BloqueoDelSitio, Cliente, FichaInvalida, consultar_comparador,
                     parsear_ficha, parsear_listado, url_listado)

RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HONDURAS = dt.timezone(dt.timedelta(hours=-6))
PILOTO_INSTITUCIONES = ["11060"]
PILOTO_FICHAS = [142, 1051]
ENCABEZADO_REGISTRO = "<!-- registro:entradas -->"
TIPOS_CONOCIDOS = {"lista", "lugares", "tabla"}
DATOS_CONOCIDOS = {"responsable", "objetivo", "dirigido a"}


def normalizar(s):
    s = unicodedata.normalize("NFC", s or "")
    return " ".join(s.casefold().split())


def ahora():
    return dt.datetime.now(HONDURAS)


class Extraccion:
    def __init__(self, raiz, cliente, modo, instituciones=None, fichas=None, momento=None):
        self.raiz = raiz
        self.cliente = cliente
        self.modo = modo
        self.instituciones_pedidas = [str(x) for x in (instituciones or [])]
        self.fichas_pedidas = [int(x) for x in (fichas or [])]
        self.momento = momento or ahora()
        self.extraido = self.momento.strftime("%Y-%m-%dT%H:%M")
        self.hoy = self.momento.strftime("%Y-%m-%d")
        self.estado = self._leer_json("estado/catalogo.json", {"version": 1, "tramites": {}, "instituciones": {}})
        self.inst_por_nombre = {}
        self.listado = {}          # id -> tarjeta del listado
        self.listado_completo = False
        self.comparador, self.comparador_err = {}, {}
        self.r = {"nuevos": [], "modificados": [], "desaparecidos": [], "reaparecidos": [], "sin_cambios": 0,
                  "errores": [], "avisos": [], "procesados": 0}
        self.inicio = time.monotonic()

    # -- archivos -------------------------------------------------------------
    def ruta(self, rel):
        return os.path.join(self.raiz, rel)

    def _leer_json(self, rel, defecto):
        try:
            with open(self.ruta(rel), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return defecto

    def _leer(self, rel):
        try:
            with open(self.ruta(rel), encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def escribir(self, rel, contenido) -> bool:
        """Escribe solo si el contenido cambió. Devuelve True si escribió."""
        if self._leer(rel) == contenido:
            return False
        destino = self.ruta(rel)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        tmp = destino + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
        os.replace(tmp, destino)
        return True

    def guardar_estado(self):
        self.escribir("estado/catalogo.json", json.dumps(self.estado, ensure_ascii=False, indent=1, sort_keys=True) + "\n")

    # -- catálogo ---------------------------------------------------------------
    def _registrar_instituciones(self, pares):
        for id_, nombre in pares:
            self.inst_por_nombre.setdefault(normalizar(nombre), (id_, nombre))

    def _leer_listado(self, institucion=None):
        """Recorre todas las páginas de un listado. Devuelve True si no hubo errores."""
        pagina, total, ok = 1, 1, True
        while pagina <= total:
            url = url_listado(pagina, institucion)
            try:
                resp = self.cliente.obtener(url, aceptar_404=False)
                datos = parsear_listado(resp.texto)
            except BloqueoDelSitio:
                raise
            except Exception as e:  # noqa: BLE001
                self.r["errores"].append({"donde": url, "error": f"{type(e).__name__}: {e}"})
                ok = False
                pagina += 1
                continue
            self._registrar_instituciones(datos["instituciones"])
            total = max(total, datos["paginas"])
            for t in datos["tramites"]:
                if institucion:
                    t["institucion_id"] = institucion
                self.listado.setdefault(t["id"], t)
            pagina += 1
        return ok

    def catalogo(self):
        if self.modo == "completo":
            self.listado_completo = self._leer_listado()
            return sorted(self.listado)
        ok = True
        for inst in self.instituciones_pedidas:
            ok = self._leer_listado(inst) and ok
        ids = set(self.listado)
        if not self.inst_por_nombre:
            # las fichas sueltas necesitan la lista de instituciones del filtro del portal
            self._leer_listado_primera()
        ids.update(self.fichas_pedidas)
        return sorted(ids)

    def _leer_listado_primera(self):
        try:
            resp = self.cliente.obtener(url_listado(1), aceptar_404=False)
            self._registrar_instituciones(parsear_listado(resp.texto)["instituciones"])
        except BloqueoDelSitio:
            raise
        except Exception as e:  # noqa: BLE001
            self.r["errores"].append({"donde": url_listado(1), "error": f"{type(e).__name__}: {e}"})

    # -- instituciones ------------------------------------------------------------
    def institucion(self, nombre_ficha, id_listado=None):
        """Devuelve el registro fijo de la institución (carpeta y nota no cambian una vez creadas)."""
        id_inst, nombre = None, nombre_ficha
        if id_listado:
            id_inst = str(id_listado)
            for _id, nom in self.inst_por_nombre.values():
                if _id == id_inst:
                    nombre = nom
                    break
        else:
            par = self.inst_por_nombre.get(normalizar(nombre_ficha))
            if par:
                id_inst, nombre = par
        clave = id_inst or "nombre:" + normalizar(nombre_ficha)
        reg = self.estado["instituciones"].get(clave)
        if reg is None:
            carpeta = N.CARPETA_RAIZ + "/" + N.limpiar_nombre(nombre)
            reg = {"nombre": nombre, "id": id_inst, "carpeta": carpeta, "nota": N.nombre_nota_institucion(nombre),
                   "url_listado": url_listado(1, id_inst) if id_inst else None}
            self.estado["instituciones"][clave] = reg
        else:
            reg["nombre"] = nombre
        return clave, reg

    # -- fichas -------------------------------------------------------------------
    def procesar(self, id_):
        url = URL_FICHA.format(id=id_)
        try:
            resp = self.cliente.obtener(url)
            if resp.estado == 404:
                raise FichaInvalida("la ficha devolvió 404")
            ficha = parsear_ficha(resp.texto, id_)
        except BloqueoDelSitio:
            raise
        except Exception as e:  # noqa: BLE001
            self.r["errores"].append({"donde": url, "error": f"{type(e).__name__}: {e}"})
            return
        self.r["procesados"] += 1
        self._revisar_estructura(ficha)
        previo = self.estado["tramites"].get(str(id_))
        tarjeta = self.listado.get(id_, {})
        clave_inst, inst = self.institucion(ficha["institucion"] or tarjeta.get("institucion", ""), tarjeta.get("institucion_id"))
        comp = self.comparador.get(id_)
        comp_error = self.comparador_err.get(id_)
        if comp is None and previo and previo.get("comparador"):
            comp = previo["comparador"]          # se conserva el último dato obtenido del comparador
        if comp and comp.get("siglas_institucion") and not inst.get("siglas"):
            inst["siglas"] = comp["siglas_institucion"]

        url_final, error_final = None, None
        acc = ficha.get("accion")
        if acc and acc.get("url"):
            url_final, error_final = self.cliente.resolver_url_final(acc["url"])
            if url_final is None and previo and previo.get("url_accion") == acc["url"] and previo.get("url_final_accion"):
                url_final = previo["url_final_accion"]   # se conserva el último valor verificado
            if error_final:
                self.r["avisos"].append(f"TR-{id_}: no se pudo seguir el botón de acción ({error_final}).")

        h = N.huella(ficha, url_final, comp)
        secciones = N.secciones(ficha, url_final, comp)
        if previo:
            archivo = previo["archivo"]
        else:
            archivo = f"{inst['carpeta']}/{N.nombre_nota_tramite(id_, ficha['titulo'])}.md"
        reaparece = bool(previo and previo.get("estado_portal") == N.YA_NO_APARECE)
        cambio = (previo is None or previo.get("huella") != h or reaparece or self._leer(archivo) is None)
        if cambio:
            texto = N.render_tramite(ficha, N.enlace(inst["carpeta"], inst["nota"], inst["nombre"]), self.extraido,
                                     url_final, error_final, comp, comp_error)
            self.escribir(archivo, texto)
            self._guardar_ficha(id_, ficha)
            if previo is None:
                self.r["nuevos"].append({"id": id_, "titulo": ficha["titulo"], "archivo": archivo})
            elif reaparece:
                self.r["reaparecidos"].append({"id": id_, "titulo": ficha["titulo"]})
            if previo is not None and previo.get("huella") != h:
                antes = previo.get("secciones", {})
                cambiadas = [k for k in secciones if antes.get(k) != secciones[k]]
                cambiadas += [f"{k} (ya no aparece)" for k in antes if k not in secciones]
                self.r["modificados"].append({"id": id_, "titulo": ficha["titulo"], "secciones": cambiadas})
        else:
            self.r["sin_cambios"] += 1
        self.estado["tramites"][str(id_)] = {
            "archivo": archivo,
            "titulo": ficha["titulo"],
            "institucion": clave_inst,
            "modalidad": ficha.get("modalidad") or "",
            "huella": h,
            "secciones": secciones,
            "estado_portal": N.VIGENTE,
            "no_aparece_desde": None,
            "extraido": self.extraido if cambio else (previo or {}).get("extraido", self.extraido),
            "url_accion": (acc or {}).get("url"),
            "url_final_accion": url_final,
            "comparador": comp,
        }

    def _guardar_ficha(self, id_, ficha):
        self.escribir(f"estado/fichas/{id_}.json", json.dumps(ficha, ensure_ascii=False, indent=1, sort_keys=True) + "\n")

    def _revisar_estructura(self, ficha):
        """Avisa si el portal muestra algo que el crawler no conoce, para revisarlo a mano."""
        for d in ficha["datos"]:
            if normalizar(d["titulo"]) not in DATOS_CONOCIDOS:
                self.r["avisos"].append(f"TR-{ficha['id_portal']}: dato nuevo en la ficha «{d['titulo']}». Se copió tal cual.")
        for p in ficha["pestanas"]:
            if p["contenido"]["tipo"] not in TIPOS_CONOCIDOS:
                self.r["avisos"].append(f"TR-{ficha['id_portal']}: la pestaña «{p['etiqueta']}» tiene un formato no reconocido. Se copió como texto.")

    def marcar_desaparecidos(self, presentes):
        if self.modo != "completo":
            return
        vigentes_antes = [k for k, v in self.estado["tramites"].items() if v.get("estado_portal") == N.VIGENTE]
        faltan = [k for k in vigentes_antes if int(k) not in presentes]
        if not self.listado_completo or not presentes or len(presentes) < 0.5 * len(vigentes_antes):
            if faltan:
                self.r["avisos"].append(
                    f"No se marcó ningún trámite como desaparecido: el listado no se leyó completo o trajo muy pocos resultados "
                    f"({len(presentes)} frente a {len(vigentes_antes)} conocidos).")
            return
        for k in faltan:
            reg = self.estado["tramites"][k]
            ficha = self._leer_json(f"estado/fichas/{k}.json", None)
            inst = self.estado["instituciones"].get(reg["institucion"], {})
            if ficha is None:
                self.r["errores"].append({"donde": reg["archivo"], "error": "falta la copia de la ficha para marcarla como desaparecida"})
                continue
            texto = N.render_tramite(ficha, N.enlace(inst.get("carpeta", N.CARPETA_RAIZ), inst.get("nota", ""), inst.get("nombre", "")),
                                     reg.get("extraido", self.extraido), reg.get("url_final_accion"), None,
                                     reg.get("comparador"), None, N.YA_NO_APARECE, self.hoy)
            self.escribir(reg["archivo"], texto)
            reg["estado_portal"] = N.YA_NO_APARECE
            reg["no_aparece_desde"] = self.hoy
            self.r["desaparecidos"].append({"id": int(k), "titulo": reg["titulo"]})

    # -- notas generales ------------------------------------------------------------
    def notas_generales(self):
        por_inst = {}
        for k, t in self.estado["tramites"].items():
            por_inst.setdefault(t["institucion"], []).append({
                "id": int(k), "titulo": t["titulo"], "nota": os.path.basename(t["archivo"])[:-3],
                "modalidad": t.get("modalidad", ""), "estado_portal": t["estado_portal"],
                "no_aparece_desde": t.get("no_aparece_desde")})
        indice = []
        for clave, filas in por_inst.items():
            inst = self.estado["instituciones"][clave]
            texto = N.render_institucion(inst["nombre"], inst.get("id"), inst.get("url_listado"), filas, inst.get("siglas"))
            self.escribir(f"{inst['carpeta']}/{inst['nota']}.md", texto)
            vig = sum(1 for f in filas if f["estado_portal"] == N.VIGENTE)
            indice.append((N.enlace(inst["carpeta"], inst["nota"], inst["nombre"]), inst["nombre"], vig, len(filas) - vig))
        self.escribir(f"{N.CARPETA_RAIZ}/Índice de trámites.md", N.render_indice(indice))
        self.escribir(f"{N.CARPETA_RAIZ}/Trámites.base", N.BASE_TRAMITES)

    def reportes(self, fallo_general=None):
        r = self.r
        dur = time.monotonic() - self.inicio
        modos = {"piloto": "Prueba piloto", "completo": "Catálogo completo"}
        L = ["---", "tipo: sistema", "---", "", "# Última extracción", "",
             "| Dato | Valor |", "| --- | --- |",
             f"| Fecha y hora | {self.extraido.replace('T', ' ')} (hora de Honduras) |",
             f"| Modo | {modos.get(self.modo, self.modo)} |",
             f"| Trámites en el listado leído | {len(self.listado)} |",
             f"| Fichas leídas | {r['procesados']} |",
             f"| Nuevos | {len(r['nuevos'])} |",
             f"| Modificados | {len(r['modificados'])} |",
             f"| Sin cambios | {r['sin_cambios']} |",
             f"| Ya no aparecen (marcados en esta corrida) | {len(r['desaparecidos'])} |",
             f"| Vuelven a aparecer | {len(r['reaparecidos'])} |",
             f"| Errores | {len(r['errores'])} |",
             f"| Peticiones al portal y a los botones de acción | {self.cliente.peticiones} |",
             f"| Duración | {dur / 60:.1f} minutos |", ""]
        if fallo_general:
            L += ["> [!danger] La corrida se detuvo", f"> {fallo_general}", "> No se modificó ninguna ficha después del fallo.", ""]
        L += ["## Totales por institución", ""]
        conteo = {}
        for k, t in self.estado["tramites"].items():
            if self.modo == "completo" and int(k) not in self.listado:
                continue
            if self.modo != "completo" and int(k) not in set(self.listado) | set(self.fichas_pedidas):
                continue
            inst = self.estado["instituciones"][t["institucion"]]
            conteo[inst["nombre"]] = conteo.get(inst["nombre"], 0) + 1
        L += ["| Institución | Trámites |", "| --- | --- |"]
        L += [f"| {N.celda(n)} | {c} |" for n, c in sorted(conteo.items(), key=lambda x: x[0].lower())] or ["| Sin datos | 0 |"]
        L.append("")
        for titulo, clave in (("Nuevos", "nuevos"), ("Modificados", "modificados"), ("Ya no aparecen", "desaparecidos"),
                              ("Vuelven a aparecer", "reaparecidos")):
            if r[clave]:
                L += [f"## {titulo}", ""]
                for x in r[clave]:
                    extra = f" · {', '.join(x['secciones'])}" if x.get("secciones") else ""
                    L.append(f"- TR-{x['id']} {N.md(x['titulo'])}{extra}")
                L.append("")
        L += ["## Errores", ""]
        L += [f"- {N.md(e['donde'])}: {N.md(e['error'])}" for e in r["errores"]] or ["Sin errores."]
        L += ["", "## Avisos", ""]
        L += [f"- {N.md(a)}" for a in r["avisos"]] or ["Sin avisos."]
        L.append("")
        self.escribir(f"{N.CARPETA_SISTEMA}/Última extracción.md", "\n".join(L))

        # Registro de cambios: la entrada más reciente va arriba
        rel = f"{N.CARPETA_SISTEMA}/Registro de cambios.md"
        actual = self._leer(rel) or ("---\ntipo: sistema\n---\n\n# Registro de cambios\n\n"
                                     "Cambios detectados en el portal, por corrida. La entrada más reciente va arriba.\n\n"
                                     + ENCABEZADO_REGISTRO + "\n")
        E = [f"## {self.extraido.replace('T', ' ')} · {modos.get(self.modo, self.modo)}", ""]
        for x in r["nuevos"]:
            E.append(f"- Nuevo: TR-{x['id']} {N.md(x['titulo'])}")
        for x in r["modificados"]:
            E.append(f"- Modificado: TR-{x['id']} {N.md(x['titulo'])} · {', '.join(x['secciones']) or 'sin detalle'}")
        for x in r["desaparecidos"]:
            E.append(f"- Ya no aparece en el portal: TR-{x['id']} {N.md(x['titulo'])}")
        for x in r["reaparecidos"]:
            E.append(f"- Vuelve a aparecer: TR-{x['id']} {N.md(x['titulo'])}")
        if fallo_general:
            E.append(f"- Corrida detenida: {N.md(fallo_general)}")
        if len(E) == 2:
            E.append("- Sin cambios en las fichas.")
        E.append("")
        bloque = "\n".join(E)
        if ENCABEZADO_REGISTRO in actual:
            nuevo = actual.replace(ENCABEZADO_REGISTRO + "\n", ENCABEZADO_REGISTRO + "\n\n" + bloque, 1)
        else:
            nuevo = actual.rstrip("\n") + "\n\n" + bloque
        self.escribir(rel, nuevo)

    # -- corrida ------------------------------------------------------------------
    def ejecutar(self):
        fallo = None
        try:
            ids = self.catalogo()
            self.comparador, self.comparador_err = consultar_comparador(self.cliente, ids)
            if self.comparador_err:
                muestra = ", ".join(str(k) for k in sorted(self.comparador_err)[:15])
                self.r["avisos"].append(f"El comparador del portal no respondió para {len(self.comparador_err)} trámites "
                                        f"({muestra}{'…' if len(self.comparador_err) > 15 else ''}); se conserva el último dato conocido.")
            for id_ in ids:
                self.procesar(id_)
            self.marcar_desaparecidos(set(self.listado))
        except BloqueoDelSitio as e:
            fallo = f"El portal respondió con una verificación o bloqueo: {e}. No se intentó saltarlo."
        self.notas_generales()
        self.guardar_estado()
        self.reportes(fallo)
        return 2 if fallo else 0


def sonda(raiz, cliente):
    """Comprueba el acceso al portal y guarda el HTML crudo para las pruebas."""
    destino = os.path.join(raiz, "pruebas", "html", "crudo")
    os.makedirs(destino, exist_ok=True)
    salida = 0
    for nombre, url in (("listado-pagina-1.html", url_listado(1)), ("listado-11060.html", url_listado(1, "11060")),
                        ("ficha-1051.html", URL_FICHA.format(id=1051)), ("ficha-142.html", URL_FICHA.format(id=142))):
        try:
            r = cliente.obtener(url, aceptar_404=False)
            with open(os.path.join(destino, nombre), "w", encoding="utf-8", newline="") as f:
                f.write(r.texto)
            detalle = ""
            if nombre.startswith("ficha"):
                ficha = parsear_ficha(r.texto, int(nombre[6:-5]))
                detalle = f"ficha leída: «{ficha['titulo']}», {len(ficha['pestanas'])} pestañas"
            else:
                datos = parsear_listado(r.texto)
                detalle = f"{len(datos['tramites'])} trámites en la página, {datos['paginas']} páginas, {len(datos['instituciones'])} instituciones en el filtro"
            print(f"OK   {r.estado} {url} · {detalle}")
        except BloqueoDelSitio as e:
            print(f"BLOQUEADO {url} · {e}")
            salida = 2
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {url} · {type(e).__name__}: {e}")
            salida = max(salida, 1)
    try:
        datos, err = consultar_comparador(cliente, [1051, 142])
        print(f"OK   comparador · {len(datos)} trámites con datos" + (f" · errores: {err}" if err else ""))
    except BloqueoDelSitio as e:
        print(f"BLOQUEADO comparador · {e}")
        salida = 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR comparador · {type(e).__name__}: {e}")
        salida = max(salida, 1)
    print("Resultado:", {0: "el portal responde desde aquí", 1: "hubo errores", 2: "el portal bloquea estas conexiones"}[salida])
    return salida


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extrae las fichas del Portal de Trámites del Estado de Honduras")
    ap.add_argument("--modo", choices=["sonda", "piloto", "completo"], default="piloto")
    ap.add_argument("--instituciones", help="IDs del filtro de institución, separados por coma (modo piloto)")
    ap.add_argument("--fichas", help="IDs de fichas sueltas, separados por coma (modo piloto)")
    ap.add_argument("--pausa", type=float, default=float(os.environ.get("PAUSA", "2.5")))
    ap.add_argument("--raiz", default=RAIZ_REPO)
    a = ap.parse_args(argv)
    cliente = Cliente(pausa=a.pausa, registro=lambda m: print("  ", m, flush=True))
    if a.modo == "sonda":
        return sonda(a.raiz, cliente)
    inst = a.instituciones.split(",") if a.instituciones else (PILOTO_INSTITUCIONES if a.modo == "piloto" else [])
    fichas = [int(x) for x in a.fichas.split(",")] if a.fichas else (PILOTO_FICHAS if a.modo == "piloto" else [])
    ex = Extraccion(a.raiz, cliente, a.modo, inst, fichas)
    codigo = ex.ejecutar()
    r = ex.r
    print(f"Listado: {len(ex.listado)} · leídas: {r['procesados']} · nuevas: {len(r['nuevos'])} · modificadas: {len(r['modificados'])} · "
          f"sin cambios: {r['sin_cambios']} · ya no aparecen: {len(r['desaparecidos'])} · errores: {len(r['errores'])}")
    for e in r["errores"]:
        print("  ERROR", e["donde"], e["error"])
    return codigo


if __name__ == "__main__":
    sys.exit(main())
