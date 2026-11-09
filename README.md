# Trámites del Estado para Case Deck

Crawler que copia una vez al mes las fichas del Portal de Trámites del Estado de Honduras (DIGER, tramites.diger.gob.hn) y las convierte en notas de Obsidian, ordenadas por institución, para la carpeta `10 Trámites del Estado` de la bóveda Case Deck. Es material de consulta: se enlaza con los casos pero no forma parte del control de casos.

La salida son únicamente archivos `.md` (más la vista `Trámites.base`). No usa Supabase, CSV ni Excel, y solo depende de la biblioteca estándar de Python.

## Cómo funciona

```
Portal de Trámites ──(GitHub Actions, día 3 de cada mes)──> este repositorio
                                                              │
                                     git pull cada hora (CaseDeck Motor)
                                                              ▼
                            ~/tramites-estado en la Mac ──(puente)──> bóveda/10 Trámites del Estado
```

1. **GitHub Actions** corre el crawler el día 3 de cada mes a las 03:17 de Honduras (09:17 UTC) y guarda en este repositorio solo las notas que cambiaron.
2. **En la Mac**, el repositorio vive en `~/tramites-estado`, fuera de OneDrive. Nunca hay una carpeta `.git` dentro de la bóveda.
3. **El puente** corre al final de cada ejecución de la app CaseDeck Motor, que ya tiene Acceso total al disco. Baja las novedades y copia a la bóveda solo lo que cambió, sin tocar tus notas propias. Ni Python ni Terminal necesitan permisos especiales.

## Contenido

| Ruta | Qué es |
| --- | --- |
| `crawler/` | Lectura del portal (`portal.py`), armado de notas (`notas.py`) y corrida (`extraer.py`) |
| `puente/puente_tramites.py` | Puente entre el repositorio y la bóveda |
| `puente/instalar_puente.sh` | Engancha el puente a CaseDeck Motor (un renglón en `ejecutar.sh`) |
| `puente/desinstalar_puente.sh` | Quita ese renglón; no borra notas |
| `.github/workflows/extraer.yml` | Corrida mensual y manual en GitHub Actions |
| `gaceta/` y `.github/workflows/gaceta-sonda.yml` | Primera etapa de la sección de normativa: sonda de La Gaceta (ENAG). No escribe notas |
| `docs/documentacion-crawler.md` | Documentación; el crawler la copia a `10 Trámites del Estado/_Sistema/Documentación del crawler.md` |
| `pruebas/` | 29 pruebas con HTML guardado del portal y con una bóveda simulada |
| `10 Trámites del Estado/` | Salida del crawler (la crea la primera corrida) |
| `estado/` | Registro interno: huellas, nombres de archivo fijos y copia de cada ficha leída |

## Paso a paso

Hacé un paso a la vez y mandá una captura si algo no se ve igual a lo que dice aquí.

### 0. Correo privado en GitHub (una sola vez)

El repositorio es público, así que conviene que tus cambios no muestren tu correo. En GitHub entrá a tu foto (arriba a la derecha) → **Settings** → **Emails** y activá **Keep my email addresses private**.

### 1. Crear el repositorio

1. En github.com, botón **+** (arriba a la derecha) → **New repository**.
2. **Repository name**: `tramites-estado`. Elegí **Public**. No marqués **Add a README**.
3. Clic en **Create repository**.

### 2. Subir el código

1. Descomprimí `tramites-estado.zip` en **Descargas** (doble clic). Va a quedar la carpeta `Descargas/tramites-estado`.
2. Abrí esa carpeta en Finder y presioná **Cmd + Shift + .** (punto) para ver las carpetas ocultas. Tiene que aparecer `.github`.
3. En la página del repositorio nuevo, clic en el enlace **uploading an existing file**.
4. En Finder, dentro de `tramites-estado`, presioná **Cmd + A** y arrastrá todo a la página de GitHub. Esperá que termine la carga.
5. Abajo, clic en **Commit changes**.
6. Revisá que en el repositorio aparezca la carpeta `.github/workflows` con el archivo `extraer.yml`. Si no aparece, avisame y lo creamos desde **Add file → Create new file**.

### 3. Probar si el portal responde desde GitHub (sonda)

1. En el repositorio, pestaña **Actions**. Si GitHub pregunta si querés activar los flujos de trabajo, aceptá.
2. A la izquierda, **Extraer trámites del Estado** → botón **Run workflow** → en **modo** dejá `sonda` → **Run workflow**.
3. Esperá un par de minutos, entrá a la corrida y abrí el paso **Extracción (sonda)**.
4. Si al final dice `el portal responde desde aquí`, seguí. Si dice `el portal bloquea estas conexiones`, no sigás: mandame la captura y pasamos el crawler a tu Mac.

### 4. Prueba piloto

Igual que el paso 3, pero con **modo** `piloto`. Lee la institución 11060 (Secretaría de Trabajo y Seguridad Social) y las fichas 142 y 1051. Al terminar, el repositorio tiene la carpeta `10 Trámites del Estado`.

### 5. Instalar el puente en la Mac

Abrí **Terminal** y pegá un comando a la vez (Cmd + V, Enter, y esperá que vuelva a aparecer el `%`).

```
cd ~
```

Cambiá `TU_USUARIO` por tu usuario de GitHub:

```
git clone https://github.com/TU_USUARIO/tramites-estado.git
```

```
bash ~/tramites-estado/puente/instalar_puente.sh
```

El instalador corre las pruebas del puente, agrega su renglón a CaseDeck Motor y lo ejecuta una vez. Al final tiene que mostrar una línea que empieza con `Puente:` y dice cuántas notas copió.

### 6. Revisar en Obsidian

Abrí la carpeta `10 Trámites del Estado`, revisá la nota de la 1051 y `_Sistema/Última extracción`. Si el formato está bien, seguí.

### 7. Catálogo completo

En GitHub, **Run workflow** con **modo** `completo`. Tarda unos 25 minutos por las pausas entre peticiones. Las notas llegan a la bóveda en la siguiente corrida de CaseDeck Motor (cada hora de 7:05 a 20:05) o al dar doble clic en `07 Sistema/Actualizar ahora.command`.

Desde ahí, la corrida mensual es automática.

## Si algo falla

| Síntoma | Qué hacer |
| --- | --- |
| La sonda dice que el portal bloquea las conexiones | El crawler se pasa a la Mac con el mismo esquema del motor. Avisame. |
| El paso "Guardar los cambios" falla con un error de permiso | En el repositorio: **Settings → Actions → General → Workflow permissions → Read and write permissions → Save**, y volvé a correr. |
| No llegan notas a la bóveda | En Terminal: `tail -20 ~/Library/Application\ Support/CaseDeck/logs/puente_tramites.log` |
| Reinstalaste Case Deck con su `instalar.sh` | Ese instalador reescribe `ejecutar.sh`. Volvé a correr `bash ~/tramites-estado/puente/instalar_puente.sh`. |
| Querés apagar el puente | `bash ~/tramites-estado/puente/desinstalar_puente.sh` (no borra notas). |
| GitHub desactivó la corrida mensual | En repositorios públicos GitHub desactiva las corridas programadas tras 60 días sin actividad. Cada corrida guarda un cambio en el Registro de cambios, así que no debería pasar; si pasa, se reactiva en **Actions** con un clic. |

## Respeto al sitio

Pausa de 2,5 a 3,5 segundos entre peticiones, tres reintentos con espera creciente, agente que identifica el proyecto sin datos personales, ninguna cookie ni inicio de sesión, y alto inmediato si el sitio responde con una verificación anti robots. Solo se leen páginas públicas. El portal no tiene `robots.txt` (responde 404).

## Pruebas

```
python3 -m unittest discover -s pruebas -v
```

Corren solas en cada ejecución de GitHub Actions antes de leer el portal. Si alguna falla, la extracción no corre.

La documentación completa está en `docs/documentacion-crawler.md`, y en la bóveda en `10 Trámites del Estado/_Sistema/Documentación del crawler.md`.

Ningún archivo o carpeta con tildes se sube a mano: los crea el crawler en GitHub. Si se suben desde la Mac por la web, las tildes llegan en otra forma Unicode y GitHub muestra dos carpetas con el mismo nombre.
