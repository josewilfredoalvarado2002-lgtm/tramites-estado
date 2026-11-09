#!/bin/bash
# Instala el puente de trámites (opción A): agrega un renglón al final de la lista de tareas
# de la app CaseDeck Motor para que, después del motor, copie a la bóveda las fichas que cambiaron.
# No crea permisos nuevos ni tareas programadas nuevas.
#
# Uso:  bash ~/tramites-estado/puente/instalar_puente.sh
#       (opcional) bash ~/tramites-estado/puente/instalar_puente.sh "/ruta/de/la/bóveda"
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOPORTE="$HOME/Library/Application Support/CaseDeck"
EJECUTAR="$SOPORTE/ejecutar.sh"
LOGS="$SOPORTE/logs"
BOVEDA="${1:-$HOME/Library/CloudStorage/OneDrive-Personal/Case Deck/Case Deck}"
MARCA="# puente-tramites"
ETIQUETA="com.casedeck.motor"

echo ""
echo "== Puente de trámites: instalación =="
echo "Repositorio: $REPO"
echo "Bóveda:      $BOVEDA"
echo ""

# 1. Comprobaciones
if [ ! -f "$EJECUTAR" ]; then
  echo "No encontré $EJECUTAR."
  echo "Primero tiene que estar instalado Case Deck con su app CaseDeck Motor."
  exit 1
fi
case "$REPO" in
  *"/Library/CloudStorage/"*|*"/Library/Mobile Documents/"*|"$BOVEDA"*)
    echo "El repositorio no puede estar en OneDrive, en iCloud ni dentro de la bóveda."
    echo "Clonalo en tu carpeta de inicio, por ejemplo ~/tramites-estado, y volvé a correr este instalador."
    exit 1
    ;;
esac
if [ ! -d "$REPO/.git" ]; then
  echo "Esta carpeta no es un repositorio clonado con git: $REPO"
  exit 1
fi

PY=""
for c in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "No encontré Python 3.9 o superior. Ejecutá: xcode-select --install"
  exit 1
fi

# 2. Pruebas del puente con datos ficticios
echo "Ejecutando pruebas con datos ficticios..."
if ! "$PY" -m unittest discover -s "$REPO/pruebas" -p "test_puente.py" > /tmp/puente-pruebas.log 2>&1; then
  echo "ATENCIÓN: alguna prueba falló. Mandame el contenido de /tmp/puente-pruebas.log"
  exit 1
fi
echo "Pruebas: todas superadas."

# 3. Copia del puente fuera del repositorio: lo que corre con el permiso de la app no se actualiza solo desde internet
mkdir -p "$LOGS"
cp "$REPO/puente/puente_tramites.py" "$SOPORTE/puente_tramites.py"
chmod 600 "$SOPORTE/puente_tramites.py"

# 4. Configuración
"$PY" - "$SOPORTE/puente_tramites.json" "$REPO" "$BOVEDA" <<'EOF'
import json, os, sys
ruta, repo, boveda = sys.argv[1:4]
cfg = {}
if os.path.exists(ruta):
    with open(ruta, encoding="utf-8") as f:
        cfg = json.load(f)
cfg.update({"repositorio": repo, "boveda": boveda})
cfg.setdefault("actualizar_repositorio", True)
cfg.setdefault("minutos_de_gracia", 10)
cfg.setdefault("segundos_git", 60)
with open(ruta, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print("Configuración guardada en", ruta)
EOF

# 5. Renglón en la lista de tareas de CaseDeck Motor (una sola vez)
if grep -q "$MARCA" "$EJECUTAR"; then
  echo "El renglón del puente ya estaba en ejecutar.sh."
else
  cp "$EJECUTAR" "$EJECUTAR.antes-del-puente"
  {
    echo "$MARCA: copia a la bóveda las fichas de trámites que cambiaron (lo agregó instalar_puente.sh)"
    echo "\"$PY\" \"$SOPORTE/puente_tramites.py\" >> \"$LOGS/puente_tramites.log\" 2>&1 || true"
  } >> "$EJECUTAR"
  echo "Renglón agregado al final de ejecutar.sh (copia de respaldo: ejecutar.sh.antes-del-puente)."
fi

# 6. Primera corrida a través de CaseDeck Motor, que es la app con Acceso total al disco
echo ""
echo "Ejecutando CaseDeck Motor para la primera copia (puede tardar un par de minutos)..."
LOG="$LOGS/puente_tramites.log"
N=0
if [ -f "$LOG" ]; then N=$(wc -l < "$LOG" | tr -d ' '); fi
launchctl kickstart -k "gui/$(id -u)/$ETIQUETA" >/dev/null 2>&1 || true
for _ in $(seq 1 120); do
  sleep 2
  if [ -f "$LOG" ] && tail -n +$((N + 1)) "$LOG" | grep -qE "Puente:|ERROR"; then break; fi
done
echo ""
if [ -f "$LOG" ]; then
  tail -n +$((N + 1)) "$LOG"
else
  echo "Todavía no hay bitácora del puente. Revisá en unos minutos: tail -20 \"$LOG\""
fi
echo ""
echo "Listo. Abrí Obsidian y buscá la carpeta '10 Trámites del Estado'."
echo "Si reinstalás Case Deck con su instalar.sh, volvé a correr este instalador para reponer el renglón."
