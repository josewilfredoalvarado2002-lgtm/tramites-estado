#!/bin/bash
# Quita el renglón del puente de la lista de tareas de CaseDeck Motor.
# No borra notas de la bóveda ni el repositorio.
set -euo pipefail
SOPORTE="$HOME/Library/Application Support/CaseDeck"
EJECUTAR="$SOPORTE/ejecutar.sh"
if [ ! -f "$EJECUTAR" ]; then echo "No encontré $EJECUTAR."; exit 1; fi
cp "$EJECUTAR" "$EJECUTAR.antes-de-desinstalar-puente"
/usr/bin/python3 - "$EJECUTAR" <<'EOF'
import sys
ruta = sys.argv[1]
with open(ruta, encoding="utf-8") as f:
    lineas = f.read().split("\n")
salida, saltar = [], False
for ln in lineas:
    if ln.startswith("# puente-tramites"):
        saltar = True
        continue
    if saltar and "puente_tramites.py" in ln:
        saltar = False
        continue
    saltar = False
    salida.append(ln)
with open(ruta, "w", encoding="utf-8") as f:
    f.write("\n".join(salida))
print("Renglón del puente quitado de", ruta)
EOF
echo "El puente ya no corre. Las notas de '10 Trámites del Estado' se quedan donde están."
