---
tipo: sistema
version: 1.1.0
actualizado: 2026-11-09
---

# Documentación del crawler de trámites

Esta carpeta guarda una copia de consulta de las fichas del Portal de Trámites del Estado de Honduras (DIGER), ordenadas por institución. Sirve de contexto para los casos, pero no forma parte del control de casos: el motor de Case Deck no lee esta carpeta.

## Cómo llega la información

| Paso | Dónde corre | Qué hace |
| --- | --- | --- |
| Extracción | GitHub Actions, día 3 de cada mes a las 03:17 de Honduras (09:17 UTC), o a mano | Lee el listado general del portal, cada ficha y el comparador; escribe en el repositorio solo las notas que cambiaron |
| Puente | Tu Mac, al final de cada ejecución de CaseDeck Motor (cada hora de 7:05 a 20:05 y al iniciar sesión) | Baja las novedades del repositorio (`~/tramites-estado`) y copia a esta carpeta solo lo que cambió |

El repositorio está fuera de OneDrive y fuera de la bóveda. El puente corre con el permiso de Acceso total al disco que ya tiene CaseDeck Motor; no se le dio ese permiso a Python ni a Terminal.

## Qué se extrae

Todo tal como aparece en el portal, sin resumir, reordenar ni completar. Si un dato no aparece, la nota dice "No consta en el portal". El marco legal se copia como lo cita el portal, sin verificarlo.

| Parte de la ficha | Dónde queda en la nota |
| --- | --- |
| Título, institución, N.º, modalidad, etiquetas (por ejemplo "Aprobado"), texto y URL del botón de acción | Sección Cabecera y propiedades |
| URL final del botón después de redirecciones | Cabecera. Si el sitio de la institución no responde, dice "No se pudo verificar en la extracción" |
| Descripción | Sección Descripción |
| Responsable, Objetivo, Dirigido a | Secciones con el mismo nombre y propiedades |
| Pestañas (Pasos del trámite, Requisitos, Lugares, Entregables, Más información) | Una sección por pestaña, con el nombre que usa el portal y en su orden |
| Marco legal, costos o tasas, tiempo de respuesta | Al final de Más información. Solo se llenan si el portal los rotula; hoy ninguna ficha revisada los trae |
| Datos de la función «Comparar trámites» | Sección "Según el comparador del portal" y dos propiedades propias. No sustituyen a los datos de la ficha |
| Fecha de última actualización del portal | Sección Fuente. El portal no muestra esa fecha, así que dice "No consta en el portal" |
| Fecha y hora de extracción | Sección Fuente y propiedad `extraido` |

En Lugares, si el portal no da horario ni enlace de mapa, la nota lo dice expresamente.

Algunos correos de contacto vienen ocultos en el HTML por Cloudflare y el navegador los muestra al abrir la ficha. El crawler los decodifica igual que el navegador, así que la nota dice, por ejemplo, el correo de la unidad de becas y no "[email protected]".

## Propiedades de cada trámite

| Propiedad | Contenido |
| --- | --- |
| `tipo` | `tramite` |
| `id_portal` | Número de la ficha en el portal |
| `titulo`, `aliases` | Título oficial. Si el portal lo cambia, se actualizan estas dos y el nombre del archivo queda igual |
| `institucion` | Enlace con ruta completa a la nota de la institución en esta carpeta |
| `responsable`, `modalidad`, `dirigido_a` | Tal como aparecen; `dirigido_a` es una lista, un renglón por elemento |
| `costo`, `tiempo_respuesta` | Solo si la ficha los rotula; si no, "No consta en el portal" |
| `comparador_tiempo_dias`, `comparador_complejidad` | Lo que devuelve el comparador del portal. Se omiten si no se pudo consultar |
| `url_ficha`, `url_inicio` | Ficha en el portal y URL del botón de acción |
| `actualizado_portal` | Fecha que muestre el portal; hoy "No consta en el portal" |
| `extraido` | Fecha y hora de Honduras en que se extrajo el contenido vigente de la nota |
| `huella` | Huella SHA-256 del contenido extraído. Solo si cambia se reescribe la nota |
| `estado_portal` | `Vigente` o `Ya no aparece en el portal` |
| `no_aparece_desde` | Solo cuando el trámite dejó de aparecer |

Podés agregar tus propias propiedades a cualquier nota: el puente las conserva.

## Lo que el crawler nunca toca

- Todo lo que está debajo de `<!-- portal:fin -->`, empezando por la sección **Notas propias**.
- Las propiedades que agregués a mano, incluida `catalogo_case_deck` en las notas de institución.
- Cualquier carpeta fuera de `10 Trámites del Estado`. El puente rechaza cualquier ruta que salga de aquí.
- Las notas que modificaste hace menos de 10 minutos: se actualizan en la siguiente corrida.

Si borrás los marcadores `<!-- portal:inicio -->` o `<!-- portal:fin -->` de una nota, el puente deja de actualizarla y lo anota en su bitácora.

## Nombres de archivo

`TR-<N.º> <título>.md` dentro de la carpeta de su institución. Se quitan los caracteres que Obsidian no admite o que rompen enlaces (`\ / : * ? " < > | # ^ [ ]`). El nombre queda fijo desde la primera extracción, para que no se rompan los enlaces desde los casos.

Cada institución tiene su carpeta y una nota con su mismo nombre, que lista sus trámites. Todos los enlaces que genera el crawler llevan la ruta completa. Así no se confunden con una nota de igual nombre en `09 Catálogos/Instituciones`. Ojo con los enlaces sin ruta que escribás vos o que escriba el motor (por ejemplo `secretaria: "[[Instituto Hondureño de Transporte Terrestre]]"`). Si existen las dos notas, Obsidian puede abrir la que no es. La tabla de equivalencias marca esos casos con «mismo nombre».

## Cambios en el portal

| Situación | Qué pasa |
| --- | --- |
| La ficha no cambió | La nota no se reescribe, así que su fecha de modificación en Obsidian no se mueve |
| La ficha cambió | Se reescribe el bloque del portal y el [[Registro de cambios]] anota las secciones que cambiaron (por ejemplo, Requisitos) |
| El trámite dejó de aparecer en el listado | No se borra. Queda `estado_portal: Ya no aparece en el portal` con la fecha, y se conserva la última versión |
| Vuelve a aparecer | Vuelve a `Vigente` y queda anotado |
| El listado no se pudo leer completo | No se marca nada como desaparecido, para no equivocarse |

[[Última extracción]] resume cada corrida: fecha, totales por institución, nuevos, modificados, desaparecidos, errores y avisos. Cuando el portal muestra algo que el crawler no conoce, como un rótulo o una pestaña nueva, lo copia tal cual y deja un aviso para revisarlo.

## Relación con Case Deck

- El motor solo lee `01 Casos`, `02 Actuaciones`, `03 Clientes`, `04 Equipo` y las dos carpetas de `09 Catálogos`. No valida estas notas, no las reporta en Estado del sistema ni crea catálogos a partir de ellas. Se comprobó con una copia del motor el 5 y el 9 de noviembre de 2026: 0 errores y 0 avisos.
- Para enlazar un trámite desde un caso, escribí el enlace en el cuerpo de la nota del caso o agregá la propiedad opcional `tramites_estado` con una lista de enlaces, por ejemplo `- "[[TR-1051 Certificación de expediente en trámite]]"`. El motor no la exige ni la valida, y la conserva cuando reescribe el caso.
- No se cambió `config.json` ni `casedeck.py`. Lo único que se agregó es un renglón al final de `~/Library/Application Support/CaseDeck/ejecutar.sh` para que CaseDeck Motor llame al puente después del motor.

## Vista de grafo: dos redes unidas por una línea

- Cada trámite enlaza solo a su institución; cada institución, a sus trámites; el [[Índice de trámites]], a las instituciones.
- El índice tiene un único enlace hacia el resto de la bóveda: `[[00 Panel/Directorio|Directorio de Case Deck]]`. Esa es la línea que une las dos redes.
- Todos los enlaces que genera el crawler llevan ruta completa, así que una nota copiada con el mismo nombre en otra carpeta no se mezcla.
- Configuración recomendada del grafo (Vista de grafo → ícono de ajustes):
  - Filtros: además de lo que ya excluís, `-path:"10 Trámites del Estado/_Sistema"`.
  - Grupos: `file:"Índice de trámites"`, `[tipo:institucion_portal]` y `path:"10 Trámites del Estado"`, cada uno con su color.
  - Fuerzas: fuerza de centro baja (0,1), repulsión alta (14), fuerza de enlace alta (1) y distancia de enlace media (160). Con la fuerza de enlace en 0 los enlaces no agrupan nada y todo se ve como una sola bola.
- Los enlaces que agregués desde un caso con `tramites_estado` o desde `catalogo_case_deck` también aparecen como líneas entre las dos redes. Es lo esperado: son las relaciones reales.

## Equivalencias con tu catálogo de instituciones

[[Equivalencias de instituciones]] la genera el puente en tu Mac y nunca escribe en `09 Catálogos`. Solo propone candidatas cuyo nombre, alias o siglas coinciden exactamente (sin tildes ni mayúsculas). Para confirmar una equivalencia, abrí la nota de la institución en esta carpeta y agregá:

```
catalogo_case_deck: "[[09 Catálogos/Instituciones/Nombre de tu nota]]"
```

## Ejecutar a mano

- Extracción: en GitHub, pestaña Actions → Extraer trámites del Estado → Run workflow. Modos: `sonda` (solo prueba el acceso), `piloto` (institución 11060 y fichas 142 y 1051) y `completo`.
- Puente: doble clic en `07 Sistema/Actualizar ahora.command`, que ejecuta CaseDeck Motor y, después del motor, el puente.
- Bitácora del puente: `~/Library/Application Support/CaseDeck/logs/puente_tramites.log`.

## Respeto al sitio

Pausa de 2,5 a 3,5 segundos entre peticiones, tres reintentos con espera creciente, un agente que identifica el proyecto sin datos personales, sin cookies ni inicio de sesión, y alto inmediato si el sitio responde con una verificación anti robots. El comparador se consulta de tres en tres trámites, que es lo que el portal permite. Una corrida completa hace unas 470 peticiones y tarda unos 25 minutos.

## Limitaciones

1. Si la Mac está apagada, las notas llegan a la bóveda en la siguiente ejecución de CaseDeck Motor.
2. El portal sirve las fichas sin fecha de actualización, así que no se puede saber cuándo cambió una ficha entre dos corridas mensuales.
3. El comparador es una función del portal y no explica cómo calcula el tiempo estimado ni la complejidad.
4. Si reinstalás Case Deck con su `instalar.sh`, el renglón del puente desaparece de `ejecutar.sh`. Se repone con `bash ~/tramites-estado/puente/instalar_puente.sh`.
5. En repositorios públicos, GitHub desactiva las corridas programadas tras 60 días sin actividad. Cada corrida guarda un cambio, así que no debería pasar.
