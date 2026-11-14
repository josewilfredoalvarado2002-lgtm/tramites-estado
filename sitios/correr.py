"""
Uso:
  python correr.py SAR ONCAE CNBS          -> corre esas instituciones
  python correr.py --todas                 -> todas las de fuentes.py
  python correr.py SAR --limite 10         -> prueba: solo 10 fichas
  python correr.py SAR --destino /otra/boveda   -> escribe en otra carpeta (para pruebas)
"""
import argparse
import os
import sys

import adaptadores
from diger import comparar
from escritor import Escritor
from fuentes import FUENTES
from nucleo import Cliente, DominioNoVerificado, dominios_verificados, log

_PADRE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Destino por defecto: dentro del repositorio tramites-estado (de ahí el puente lo copia a la bóveda);
# fuera del repositorio, directo a la bóveda.
BOVEDA = os.environ.get("DESTINO") or (
    _PADRE if os.path.isdir(os.path.join(_PADRE, "10 Trámites del Estado")) and os.path.isdir(os.path.join(_PADRE, ".git"))
    else os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/Case Deck/Case Deck"))


def correr(siglas, destino, limite=None):
    fuente = dict(FUENTES[siglas], siglas=siglas)
    try:
        permitidos, reg = dominios_verificados(siglas)
    except DominioNoVerificado as e:
        log(f"{siglas}: NO SE CORRE. {e}")
        return False
    log(f"{siglas}: dominios verificados {sorted(permitidos)} — {reg['estado']}")
    cli = Cliente(permitidos)
    ad = getattr(adaptadores, fuente["adaptador"])
    params = dict(fuente["parametros"])
    if limite and fuente["adaptador"] == "descargas_wpdm":
        params["limite"] = limite
    fichas, errores = ad(cli, siglas, **params)
    if not fichas:
        log(f"{siglas}: el sitio no devolvió fichas; no se toca la bóveda.")
        return False
    comp, dig = comparar(fichas, fuente.get("id_diger"))
    esc = Escritor(destino, fuente, reg)
    completo = not errores and not limite
    resultado = esc.escribir_fichas(fichas, comp, completo)
    esc.indice(fichas, comp, dig, resultado, errores, cli.rechazadas)
    n, c, i, o, r = resultado
    log(f"{siglas}: {len(fichas)} fichas → {len(n)} nuevas, {len(c)} actualizadas, {i} sin cambios, "
        f"{len(o)} ya en DIGER, {len(r)} retiradas, {len(errores)} errores, {len(set(cli.rechazadas))} enlaces rechazados")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("siglas", nargs="*")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--destino", default=BOVEDA)
    a = ap.parse_args()
    lista = list(FUENTES) if a.todas else [s.upper() for s in a.siglas]
    if not lista:
        ap.print_help()
        sys.exit(1)
    for s in lista:
        if s not in FUENTES:
            log(f"{s}: no está en fuentes.py")
            continue
        correr(s, a.destino, a.limite)


if __name__ == "__main__":
    main()
