"""
Crawler del Portal Informativo de Gestiones - Municipalidad de San Pedro Sula
https://www.sanpedrosula.hn/gestion-informativa/

Qué hace:
  1. Recorre el listado de trámites/preguntas (paginador ASP.NET, 20 por página),
     una vez por cada Gerencia, para saber a qué gerencia pertenece cada trámite.
  2. Abre la ficha de cada uno (Tramite.aspx?id=N) y saca descripción, requisitos,
     costo, vigencia, oficina, horarios, formatos descargables, etc.
  3. Guarda todo en gestiones.csv y gestiones.json, escribe una nota de Obsidian por
     trámite (si OBSIDIAN_CARPETA está en .env) y, opcionalmente, en Supabase.

Uso:
  python crawler.py              -> corrida completa
  python crawler.py --prueba     -> solo 3 páginas del listado y sus fichas (no toca Obsidian)
  python crawler.py --solo-obsidian -> rehace las notas desde gestiones.json, sin visitar el sitio
"""
import csv
import hashlib
import json
import os
import re
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")  # oculta NotOpenSSLWarning de macOS

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE = "https://www.sanpedrosula.hn/gestion-informativa/"
FUENTE = "sanpedrosula.hn/gestion-informativa"
PAUSA = float(os.getenv("PAUSA_SEGUNDOS", "1.5"))  # respeto al servidor
MAX_PAGINAS = 200  # tope de seguridad
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
CARPETA = os.path.dirname(os.path.abspath(__file__))
CSV_SALIDA = os.path.join(CARPETA, "gestiones.csv")
JSON_SALIDA = os.path.join(CARPETA, "gestiones.json")
# Carpeta dentro de la bóveda de Obsidian donde se escriben las notas (vacío = no exportar)
OBSIDIAN_CARPETA = os.path.expanduser(os.getenv("OBSIDIAN_CARPETA", ""))

GRID = "ctl00$Contenido$GridView1"
SEL_GERENCIA = "ctl00$Contenido$ListaGerencias"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def limpiar(texto):
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


# ---------------------------------------------------------------- red
class Cliente:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        )

    def pedir(self, metodo, url, **kw):
        for intento in range(1, 4):
            try:
                r = self.s.request(metodo, url, timeout=60, **kw)
                if r.status_code == 200 and "Error de servidor" not in r.text[:3000]:
                    time.sleep(PAUSA)
                    # el sitio escribe "</br>" (mal formado) y el lector lo borraría: lo arreglamos
                    html = re.sub(r"</\s*br\s*>", "<br/>", r.text, flags=re.I)
                    return BeautifulSoup(html, "html.parser")
                log(f"  respuesta rara ({r.status_code}), intento {intento}/3")
            except requests.RequestException as e:
                log(f"  error de red: {e} (intento {intento}/3)")
            time.sleep(5 * intento)
        raise RuntimeError(f"No se pudo abrir {url}")


def campos_formulario(soup):
    """Copia los campos ocultos (__VIEWSTATE, etc.) y los combos tal como están."""
    datos = {i["name"]: i.get("value", "") for i in soup.select("#form1 input[type=hidden]") if i.get("name")}
    for sel in soup.select("#form1 select"):
        op = sel.find("option", selected=True) or sel.find("option")
        datos[sel["name"]] = op.get("value", "") if op else ""
    datos["ctl00$Contenido$Texto"] = ""
    return datos


def postback(cli, soup, target, argumento="", cambios=None):
    datos = campos_formulario(soup)
    datos.update(cambios or {})
    datos["__EVENTTARGET"] = target
    datos["__EVENTARGUMENT"] = argumento
    return cli.pedir("POST", BASE, data=datos)


# ---------------------------------------------------------------- listado
def leer_tabla(soup):
    """Devuelve filas {id, gestion, unidad, categoria} de la tabla de resultados."""
    tabla = soup.find(id="Contenido_GridView1")
    if not tabla:
        return []
    filas = []
    for tr in tabla.find_all("tr", recursive=False) or tabla.select("tr"):
        celdas = tr.find_all("td", recursive=False)
        enlace = tr.select_one("a[href^='Tramite.aspx']")
        if len(celdas) < 4 or not enlace:
            continue  # encabezado o paginador
        filas.append({
            "id_tramite": enlace["href"].split("id=")[-1],
            "gestion": limpiar(celdas[0].get_text()),
            "unidad": limpiar(celdas[1].get_text()),
            "categoria_listado": limpiar(celdas[2].get_text()),
        })
    return filas


def recorrer_listado(cli, soup, etiqueta, max_paginas):
    """Lee página 1, 2, 3... hasta que el sitio repita la misma página o venga vacía."""
    vistos, todas = set(), []
    pagina = 1
    while pagina <= max_paginas:
        if pagina > 1:
            soup = postback(cli, soup, GRID, f"Page${pagina}")
        filas = leer_tabla(soup)
        nuevas = [f for f in filas if f["id_tramite"] not in vistos]
        if not nuevas:
            break
        for f in nuevas:
            vistos.add(f["id_tramite"])
        todas.extend(nuevas)
        log(f"  {etiqueta}: página {pagina} -> {len(nuevas)} filas")
        if len(filas) < 20:
            break  # última página
        tabla = soup.find(id="Contenido_GridView1")
        if not (tabla and tabla.select("a[href*='Page$']")):
            break  # sin paginador = una sola página (pedir la 2 tumba el servidor)
        pagina += 1
    return todas


def obtener_listado(cli, prueba=False):
    inicio = cli.pedir("GET", BASE)
    gerencias = [(o.get("value"), limpiar(o.get_text()))
                 for o in inicio.select("#Contenido_ListaGerencias option") if o.get("value") not in ("", "0")]
    tope = 3 if prueba else MAX_PAGINAS

    log("Listado general (todas las gerencias)")
    general = recorrer_listado(cli, inicio, "Todas", tope)
    por_id = {f["id_tramite"]: dict(f, gerencia="") for f in general}

    if prueba:
        return list(por_id.values())

    # Segunda pasada: una por gerencia, solo para anotar a cuál pertenece cada trámite.
    # El servidor a veces da error 500 pasajero: las que fallan se reintentan en otra ronda.
    pendientes = gerencias
    for ronda in (1, 2):
        fallidas = []
        for valor, nombre in pendientes:
            log(f"Gerencia: {nombre}" + (" (reintento)" if ronda == 2 else ""))
            try:
                # sesión nueva: el servidor recuerda la última página vista y se cae (error 500)
                # si esa página no existe en la gerencia filtrada
                cli = Cliente()
                soup = cli.pedir("GET", BASE)
                soup = postback(cli, soup, SEL_GERENCIA, cambios={SEL_GERENCIA: valor})
                soup = postback(cli, soup, "ctl00$Contenido$LinkButton1", cambios={SEL_GERENCIA: valor})
                for f in recorrer_listado(cli, soup, nombre[:30], tope):
                    if f["id_tramite"] in por_id:
                        por_id[f["id_tramite"]]["gerencia"] = nombre
                    else:
                        por_id[f["id_tramite"]] = dict(f, gerencia=nombre)
            except Exception as e:  # si falla una gerencia, seguimos con las demás
                log(f"  AVISO: no se pudo leer la gerencia {nombre}: {e}")
                fallidas.append((valor, nombre))
        if not fallidas:
            break
        pendientes = fallidas
        if ronda == 1:
            log("Esperando 60 s antes de reintentar gerencias que fallaron...")
            time.sleep(60)

    # Respaldo: si un trámite quedó sin gerencia, se deduce por su unidad
    unidad_a_gerencia = {f["unidad"]: f["gerencia"] for f in por_id.values() if f["gerencia"]}
    sin = [f for f in por_id.values() if not f["gerencia"]]
    for f in sin:
        f["gerencia"] = unidad_a_gerencia.get(f["unidad"], "")
    if sin:
        log(f"  {sum(1 for f in sin if not f['gerencia'])} trámites quedaron sin gerencia identificada.")
    return list(por_id.values())


# ---------------------------------------------------------------- ficha
def texto_id(soup, ident):
    el = soup.find(id=ident)
    return limpiar(el.get_text(" ")) if el else ""


def secciones_descripcion(card):
    """Parte el cuerpo en secciones usando los títulos subrayados (DESCRIPCION, REQUISITOS...)."""
    if not card:
        return {}, ""
    # El sitio escribe "</br>" (mal formado); lo convertimos a saltos de línea antes de leer
    crudo = re.sub(r"<\s*/?\s*br\s*/?\s*>|</p>|</li>|</div>|<p[^>]*>", "\n", str(card), flags=re.I)
    card = BeautifulSoup(crudo, "html.parser")
    titulos = {limpiar(t.get_text()) for t in card.find_all(["u", "strong", "b", "h3", "h4"])
               if limpiar(t.get_text()) and limpiar(t.get_text()).upper() == limpiar(t.get_text())
               and len(limpiar(t.get_text())) < 60}
    texto_completo = card.get_text()
    secciones, actual = {}, None
    for linea in texto_completo.split("\n"):
        l = limpiar(linea)
        if not l:
            continue
        if l in titulos:
            actual = l.lower().replace(" ", "_")
            secciones.setdefault(actual, [])
        elif actual:
            secciones[actual].append(l)
        else:
            secciones.setdefault("texto", []).append(l)
    return ({k: "\n".join(v) for k, v in secciones.items()},
            "\n".join(limpiar(x) for x in texto_completo.split("\n") if limpiar(x)))


def leer_ficha(cli, id_tramite):
    url = f"{BASE}Tramite.aspx?id={id_tramite}"
    soup = cli.pedir("GET", url)
    secciones, texto = secciones_descripcion(soup.find(id="Contenido_CardBody"))
    horarios = [limpiar(li.get_text()) for li in soup.select("#open li")]
    formatos = [{"nombre": limpiar(a.get_text()), "url": BASE + a["href"]}
                for a in soup.select("#Contenido_cardFormatos a[href]")]
    return {
        "url_detalle": url,
        "titulo": texto_id(soup, "Contenido_itemTramite"),
        "tipo": texto_id(soup, "Contenido_itemTipoTramite"),
        "categoria": texto_id(soup, "Contenido_itemCategoria"),
        "vigencia": texto_id(soup, "Contenido_itemVigencia"),
        "costo": texto_id(soup, "Contenido_itemCosto"),
        "telefono": texto_id(soup, "Contenido_itemTelefono"),
        "correo": texto_id(soup, "Contenido_itemCorreo"),
        "dirigido_a": texto_id(soup, "Contenido_itemDirigido"),
        "tiempo_respuesta": texto_id(soup, "Contenido_itemTiempo"),
        "oficina": texto_id(soup, "Contenido_itemOficina"),
        "horarios": horarios,
        "secciones": secciones,
        "texto_completo": texto,
        "formatos": formatos,
    }


# ---------------------------------------------------------------- guardar
def huella(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def guardar_supabase(registros):
    if not (SUPABASE_URL and SUPABASE_KEY):
        log("Supabase no configurado (.env vacío): solo se guarda CSV/JSON.")
        return
    url = f"{SUPABASE_URL}/rest/v1/registros?on_conflict=id"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    filas = [{
        "id": r["id"],
        "codigo": r["codigo"],
        "datos": r["datos"],
        "url_detalle": r["datos"].get("url_detalle"),
        "fuente": FUENTE,
        "huella_contenido": r["huella_contenido"],
        "actualizado": datetime.utcnow().isoformat() + "Z",
    } for r in registros]
    for i in range(0, len(filas), 100):
        resp = requests.post(url, headers=headers, json=filas[i:i + 100], timeout=60)
        if resp.status_code >= 300:
            log(f"ERROR Supabase {resp.status_code}: {resp.text[:300]}")
            return
    log(f"Supabase: {len(filas)} registros guardados/actualizados.")


def guardar_archivos(registros):
    anteriores = {}
    if os.path.exists(JSON_SALIDA):
        try:
            with open(JSON_SALIDA, encoding="utf-8") as f:
                anteriores = {r["codigo"]: r["huella_contenido"] for r in json.load(f)}
        except Exception:
            pass
    nuevos = [r for r in registros if r["codigo"] not in anteriores]
    cambiados = [r for r in registros
                 if r["codigo"] in anteriores and anteriores[r["codigo"]] != r["huella_contenido"]]

    with open(JSON_SALIDA, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)

    columnas = ["codigo", "gestion", "gerencia", "unidad", "categoria", "tipo", "costo", "vigencia",
                "dirigido_a", "tiempo_respuesta", "oficina", "telefono", "correo", "horarios",
                "descripcion", "documento_que_recibe", "fundamento_juridico", "requisitos",
                "informacion_adicional", "formatos", "url_detalle"]
    with open(CSV_SALIDA, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel lee bien las tildes
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        for r in registros:
            d, s = r["datos"], r["datos"].get("secciones", {})
            w.writerow({
                "codigo": r["codigo"],
                "gestion": d.get("titulo") or d.get("gestion"),
                "gerencia": d.get("gerencia"),
                "unidad": d.get("unidad"),
                "categoria": d.get("categoria") or d.get("categoria_listado"),
                "tipo": d.get("tipo"),
                "costo": d.get("costo"),
                "vigencia": d.get("vigencia"),
                "dirigido_a": d.get("dirigido_a"),
                "tiempo_respuesta": d.get("tiempo_respuesta"),
                "oficina": d.get("oficina"),
                "telefono": d.get("telefono"),
                "correo": d.get("correo"),
                "horarios": " | ".join(d.get("horarios", [])),
                "descripcion": s.get("descripcion", s.get("texto", "")),
                "documento_que_recibe": s.get("documento_que_recibe", ""),
                "fundamento_juridico": s.get("fundamento_juridico", ""),
                "requisitos": s.get("requisitos", ""),
                "informacion_adicional": s.get("informacion_adicional", ""),
                "formatos": " | ".join(x["url"] for x in d.get("formatos", [])),
                "url_detalle": d.get("url_detalle"),
            })
    log(f"Archivos: {CSV_SALIDA} ({len(registros)} filas)")
    if anteriores:
        log(f"Cambios desde la corrida anterior: {len(nuevos)} nuevos, {len(cambiados)} modificados.")
        for r in nuevos:
            log(f"  NUEVO: [{r['codigo']}] {r['datos'].get('titulo')}")
        for r in cambiados:
            log(f"  CAMBIÓ: [{r['codigo']}] {r['datos'].get('titulo')}")


def exportar_obsidian(registros, listado_completo):
    if not OBSIDIAN_CARPETA:
        log("Obsidian no configurado (OBSIDIAN_CARPETA vacío en .env).")
        return
    import obsidian
    try:
        obsidian.exportar(registros, OBSIDIAN_CARPETA, listado_completo, log=log)
    except OSError as e:
        log(f"ERROR escribiendo en Obsidian ({OBSIDIAN_CARPETA}): {e}")


# ---------------------------------------------------------------- principal
def main():
    global CSV_SALIDA, JSON_SALIDA
    prueba = "--prueba" in sys.argv
    if prueba:  # la prueba no toca los archivos de la corrida real
        CSV_SALIDA = CSV_SALIDA.replace(".csv", "_prueba.csv")
        JSON_SALIDA = JSON_SALIDA.replace(".json", "_prueba.json")
    log(f"Inicio {'(PRUEBA)' if prueba else ''}")

    if "--solo-obsidian" in sys.argv:  # regenera las notas desde gestiones.json sin visitar el sitio
        with open(JSON_SALIDA, encoding="utf-8") as f:
            exportar_obsidian(json.load(f), listado_completo=True)
        return

    cli = Cliente()
    listado = obtener_listado(cli, prueba)
    log(f"Listado: {len(listado)} trámites/preguntas. Abriendo fichas...")

    registros, fallos = [], 0
    for n, fila in enumerate(listado, 1):
        try:
            ficha = leer_ficha(cli, fila["id_tramite"])
        except Exception as e:
            fallos += 1
            log(f"  [{n}/{len(listado)}] id={fila['id_tramite']} FALLÓ: {e}")
            continue
        datos = {**fila, **ficha}
        registros.append({
            "id": huella(f"{FUENTE}:{fila['id_tramite']}"),
            "codigo": fila["id_tramite"],
            "datos": datos,
            "huella_contenido": huella(json.dumps(ficha, ensure_ascii=False, sort_keys=True)),
        })
        if n % 25 == 0 or n == len(listado):
            log(f"  fichas leídas: {n}/{len(listado)}")

    guardar_archivos(registros)
    if not prueba:  # la prueba no toca la bóveda
        exportar_obsidian(registros, listado_completo=(fallos == 0))
    guardar_supabase(registros)
    log(f"Fin. {len(registros)} guardados, {fallos} fallidos.")


if __name__ == "__main__":
    main()
