# Trámites de los sitios institucionales

Copia a Obsidian los trámites que cada institución publica en **su propio sitio oficial**,
para cubrir lo que DIGER no tiene. Nunca resume ni corrige: copia el texto tal como está.

## Cómo se protege contra sitios falsos

- Solo lee dominios que `registro.json` marca como **verificado**
  (Fase 0: dominio .gob.hn, citado por DIGER, el sitio se identifica, enlazado por otro sitio oficial).
- Si una página redirige a otro dominio, se rechaza y queda anotado en el índice.
- Si la institución no está verificada, el crawler **no corre** para ella.

## Cómo no duplica DIGER

Compara el título de cada ficha con los trámites de DIGER de la misma institución:

- **Mismo trámite y mismos requisitos** → no crea nota; queda en la tabla "Ya estaban en DIGER" del índice.
- **Parecido, o mismo trámite con requisitos distintos** → crea la nota con `posible_equivalente_diger`
  y un aviso para que revisés cuál es el vigente.

## Cómo lee los PDF y qué guarda

`estructura.py` lee cada PDF o Word oficial y ordena su texto (literal, sin resumir) en partes:
**para qué se hace**, **requisitos**, costo, plazo, dónde se presenta, base legal, procedimiento y notas.
Reconoce los requisitos aunque el documento no tenga un título "Requisitos" (lista enumerada de documentos).

- Los PDF escaneados y las imágenes se leen con OCR en GitHub (tesseract en español). Esas notas
  llevan un aviso: el OCR puede equivocarse, hay que compararlo con el original.
- **Se descarta** (no se crea nota) lo que es solo un formulario para llenar sin requisitos, y lo
  que no es un trámite. Si ya tenía nota, queda con `estado_sitio: "Descartado: formulario o documento sin requisitos"`.
  La lista de descartados está en el índice de cada institución.
- Propiedades nuevas en cada nota: `para_que` (texto del sitio, o "No consta en el sitio") y `tiene_requisitos`.
- Sitios que arman el contenido con JavaScript (`"js"` en `fuentes.py`) se abren en un navegador (Playwright).

## Dónde quedan las notas

`10 Trámites del Estado/<Institución>/Sitio institucional/`

- `<SIGLAS>-<id> <título>.md` — una nota por trámite o formato
- `<SIGLAS> — Sitio institucional.md` — índice, comparación con DIGER y errores
- `Registro de cambios <SIGLAS>.md` — qué cambió en cada corrida

Lo que escribás bajo **## Notas propias** nunca se borra. Si un trámite desaparece del sitio,
la nota no se borra: cambia a `estado_sitio: "Ya no aparece en el sitio"`.

## Cómo correrlo

```bash
cd ~/crawlers/tramites_instituciones
.venv/bin/python -W ignore correr.py SAR ONCAE CNBS
```

Prueba rápida sin tocar la bóveda: `correr.py SAR --limite 5 --destino /tmp/prueba`

## Agregar una institución

Agregar una entrada en `fuentes.py` con el adaptador que corresponda:

- `descargas_wpdm` — WordPress con Download Manager (como SAR)
- `paginas` — lista de páginas de trámites (como ONCAE y CNBS); `dividir` = cada sección es un trámite (TSC)
- `tabla` — una fila = un trámite (SEFIN, SDE)
- `bloques` — un bloque HTML = un trámite (CONATEL, SGJD, ICF, UNAH, STSS)
- `documentos_enlazados` — un documento = un trámite (SEN, CONSUCOOP, AHAC)

Con `"js": True` (o el selector que hay que esperar) la página se abre en un navegador.

## Archivos

- `nucleo.py` — cliente con candado de dominio, ficha, lectura de PDF/Word/imagen (OCR si hay tesseract)
- `estructura.py` — ordena el texto en para qué, requisitos, costo...; detecta formularios
- `certificados_intermedios.pem` — certificados que algunos sitios oficiales no envían (DGMM)
- `adaptadores.py` — lectores por tipo de sitio
- `fuentes.py` — qué leer de cada institución
- `diger.py` — comparación contra DIGER
- `escritor.py` — notas de Obsidian
- `correr.py` — punto de entrada
