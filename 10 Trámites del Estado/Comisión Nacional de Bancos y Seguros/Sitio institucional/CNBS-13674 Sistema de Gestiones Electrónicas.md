---
tipo: "tramite"
fuente: "sitio_institucional"
id_sitio: "13674"
titulo: "Sistema de Gestiones Electrónicas"
aliases:
  - "Sistema de Gestiones Electrónicas"
institucion: "[[10 Trámites del Estado/Comisión Nacional de Bancos y Seguros/Comisión Nacional de Bancos y Seguros|Comisión Nacional de Bancos y Seguros]]"
categoria: "No consta en el sitio"
calidad: "completo"
para_que: "El Sistema de Gestiones Electrónicas de la Comisión (SGE), es la plataforma tecnológica soportada por la infraestructura tecnológica de la Comisión, para la gestión y el procesamiento de documentos electrónicos; integrando de manera sistemática el resguardo, el procesamiento y la administración de la información oficial recibida y elaborada por la Comisión, mediante el uso de expedientes electróni"
tiene_requisitos: true
url_ficha: "https://www.cnbs.gob.hn/sistema-de-gestiones-electronicas/"
documentos:
  - "https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Usuario_Firma_Documento_Acrobat_Reader.pdf"
  - "https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Configurar_Acrobat_Reader_Firma_Digital.pdf"
  - "https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Emision_Certificado_Para_Firma_Digital.pdf"
  - "https://www.cnbs.gob.hn/wp-content/uploads/2026/03/00-Guia-para-uso-de-firma-digital-WEB-de-la-CNBS-V02.pdf"
actualizado_sitio: "2026-04-13"
dominio_verificado: "cnbs.gob.hn"
verificacion_dominio: "verificado (GDIE)"
extraido: 2026-11-14T00:16
huella: "808fd08646a2f849111f9af916df8494eddc817bc9c73f61587a8a8ac010769e"
estado_sitio: "Vigente"
---
<!-- portal:inicio -->
# Sistema de Gestiones Electrónicas

> [!info] Copia del sitio oficial de Comisión Nacional de Bancos y Seguros (`cnbs.gob.hn`, verificado (GDIE)), tal como aparece en el sitio. No se resumió, completó ni verificó. El crawler reescribe este bloque cuando el sitio cambia; tus anotaciones van en Notas propias.

## Cabecera

| Dato | Según el sitio |
| --- | --- |
| Institución | Comisión Nacional de Bancos y Seguros |
| Categoría | No consta en el sitio |
| Última actualización que muestra el sitio | 2026-04-13 |
| Calidad de la extracción | completo |

> [!note] Las partes «según el documento» son el texto literal del PDF o Word oficial, ordenado bajo el encabezado que le corresponde (para qué se hace, requisitos, costo...). Lo que no se pudo ubicar queda en «Otro texto del documento».

## Requisitos (según el documento oficial)

12. Luego le aparecerá un mensaje que le indica que la solicitud ya está siendo
procesada por la autoridad certificadora de la CNBS.

13. Le mostrara a continuación la pantalla indicándole que el certificado ya fue
emitido por la autoridad certificadora de la CNBS, pero no se ha instalado
en la computadora, para realizar esa acción, hacer clic en “Instalar este
certificado”.

14. En este momento el proceso ha concluido satisfactoriamente.

15. Retornar y cerrar esta pestaña:

Consideraciones:

- Debe verificar que siempre este ejecutándose el “cnbsCAHttpListener” desde el inicio
del proceso, así como se indica en este manual, de lo contrario se le pueden
presentar los mensajes siguientes:

Verificar instalación de certificado

1. Poner en la búsqueda de Windows “mmc” (Microsoft Management Console),
hacer clic en programa.

2. En el menú de “Archivo” escoger “Agregar o quitar complemento”.

3. Seleccionar el complemento “Certificados”.

4. Seleccionar “Mi cuenta de usuario”.

5. Al regresar a la pantalla anterior, hacer clic en “Aceptar”.

6. En la sección izquierda de la ventana, hacer clic en “Certificados: usuario
actual/Personal/Certificados” y busque en la sección siguiente el certificado,
hacer doble clic en el mismo.

7. Le presentara una nueva pantalla con la descripción del certificado, la viñeta
general, le describe los propósitos de ese certificado, el dueño, y su rango
de tiempo de validez.

8. En la viñeta “Detalles”, le presenta varios datos como el número de serie,
el emisor, la fecha de inicio y hora, fecha fenal, etc, en este ejemplo se
muestra el detalle del sujeto a quien se le emitió.

9. En la viñeta “Ruta de certificación”, podrá ver toda la cadena de certificación
administrada por IFE-CNBS (Infraestructura de Firma Electrónica de la
Comisión Nacional de Bancos y Seguros).

## Requisitos (según el documento oficial) — 00-Guia-para-uso-de-firma-digital-WEB-de-la-CNBS-V02.pdf

5. Buscar y seleccionar archivo a firmar, clic en “Abrir”

6. Marcar con el puntero de la pantalla el área donde colocara la firma

7. Después de un tiempo le aparecerá su firma como una etiqueta o sello en área marcada
del documento

8. Al hacer clic en el botón “GUARDAR” le creara una copia en la carpeta de descargas

## Procedimiento (según el documento)

Pasos para la generación de certificados

Previamente habiéndose registrado en el portal del S. G. E., tanto los
administradores de interconexión como las personas a las que se les va a
generar un certificado, e instalados los certificados de confianza, hacer lo
siguiente:

1. Digitar en el Explorador https://cert.cnbs.gob.hn/ , luego le aparecerá
una pantalla así:

Aquí deberá colocar el correo electrónico del administrador de interconexión
(previamente registrado en el S.G.E.):

2. Debe digitar la clave con la que se registró y el código de verificación:

3. Le solicitara un código de verificación, así:

En su buzón de correo le aparecerá un correo como este:

Copiar y pegar o digitar el código, clic en “Enviar”.

4. Le aparece una pantalla donde le solicita ejecutar el “cnbsCAHttpListener”,
hacer clic en “cnbsCAHttpListener”.

5. En esta pantalla le solicita descargar o ejecutar el programa:

a. Si es la primera vez que utiliza este sitio, debe descargar el programa,
haciendo clic en “Run” y luego ejecutar el archivo “setup.exe”.

b. Si no es la primera vez y ya lo descargo anteriormente, solo debe hacer
clic en “launch”.

Esta acción levantara una ventana en la que no se tiene participación, solo
es de visualización.

6. Volver a la pestaña inicial y hacer clic en “Inicio”.

7. Le aparece una nueva pantalla, solicitándole el correo electrónico del
usuario al que se le va a generar el certificado (previamente registrado en
el S.G.E.) luego hacer clic en “Validar correo electrónico”.

8. Le aparece un mensaje que le informa que en ese momento está buscando
la información.

Luego le presentara la información así:

Simultáneamente se verán los pasos que se van ejecutando en la ventana
del programa.

9. Le solicitara una confirmación del usuario al que se le está generando el
certificado, debe digitar la misma clave con que se registró en el S.G.E así:

10. La clave que se tiene que digitar es la del usuario al que se la va a generar
el certificado y debe ser la misma con que se registró en el S.G.E.

11. Luego le solicitara el proveedor de servicio de encriptación.

En este caso escogemos “Microsoft Software Key Storage Provider” o
“Microsoft Enhanced Cryptographic Provider v1.0”.

Seguimos viendo los pasos en la ventana del programa:

Hacer clic en “Generar solicitud”.

## Notas (según el documento)

IMPORTANTE
Indispensable tener internet
Solamente se puede firmar en computadoras que pertenecen al dominio COMISION

1. Abrir el documento a firmar en Acrobat Reader, seleccionar Herramientas y dar clic
en Certificados

2. En la siguiente pantalla dar clic en la opción Firmar digitalmente

3. En el mensaje mostrado a continuación favor de marcar el recuadro No volver a
mostrar este mensaje y luego dar clic en aceptar.

1
2
3
4
5

4. A continuación, dentro del documento con el mouse hacer un cuadro en el cual
aparecerá una pantalla mostrando el certificado que lo identifica como firmante y
dar clic en Aceptar

6
5. La siguiente pantalla muestra la información de hora y fecha que se está firmando,
en campo “Aspecto” seleccionar “Firma-cnbs”. Dar clic en Firmar

6. Especificar dirección donde se guardará el documento ya firmado, especificar
nombre y dar clic en Guardar

7. En la imagen siguiente favor marcar el cuadro Recordar esta acción para este sitio
en todos los documentos PDF y dar clic en Permitir

6
7
8
9
8. En este momento el documento ha sido firmado y deberá aparecer similar a la
siguiente imagen

9. Para verificar si la firma es válida dar clic en la firma y seguido se desplegará una
imagen con la información del estado de la firma. Si la firma es válida dar clic en
Cerrar

10
11

## Contenido

Ingresar Ahora
Podrán registrarse como usuarios del SGE, las siguientes personas naturales:
1. Representante legal de una institución supervisada.
2. Apoderado legal de una institución supervisada.
3. Designado por una institución supervisada para recibir notificaciones de solicitud o proceso realizadas por parte de la Comisión.
4. Representante legal de una sociedad o institución no supervisada que requiera realizar un trámite o gestión ante la Comisión.
5. Apoderado legal de una sociedad o institución no supervisada que requiera realizar un trámite o gestión ante la Comisión.
6. Persona que requiera firmar electrónicamente algún documento que sea parte de una solicitud o escrito que será remitido a la Comisión.
7. Persona que requiera firmar electrónicamente algún documento que sea parte de una respuesta a una solicitud realizada por parte de la Comisión a una institución supervisada.

## ¿Qué es el SGE?

El Sistema de Gestiones Electrónicas de la Comisión (SGE), es la plataforma tecnológica soportada por la infraestructura tecnológica de la Comisión, para la gestión y el procesamiento de documentos electrónicos; integrando de manera sistemática el resguardo, el procesamiento y la administración de la información oficial recibida y elaborada por la Comisión, mediante el uso de expedientes electrónicos y la inclusión de la firma generada a través de medios electrónicos en los documentos.
Ingresar Ahora

## Ámbito de Aplicación del SGE

EL SGE aplica a las solicitudes o gestiones que presentan ante la Comisión las instituciones supervisadas, las personas naturales o jurídicas; para su trámite correspondiente conforme con la Ley y a la Normativa vigente aplicable. Asimismo, aplica a los requerimientos de información que son solicitados por este Ente Supervisor.

## Uso del SGE

El SGE será utilizado para:
1. Dar trámite y gestionar una solicitud o escrito remitido a la Comisión, por parte de una institución supervisada, persona natural o jurídica.
2. Realizar una solicitud o iniciar un proceso o trámite por parte de la Comisión a una institución supervisada.
Contenido alojado digitalmente, cifrado y protegido para ser consultado en todo tiempo y cualquier lugar.

## Registro de los Usuarios del SGE

Ingresar Ahora
Todo usuario del SGE está obligado a registrarse en el Sistema de Autenticación Único de la Comisión. La Gerencia de Tecnología de Información y Comunicación publicará en el sitio web de la Comisión videos tutoriales, con el procedimiento que los usuarios deben seguir para realizar este registro de manera remota.
Formato Electrónico de las Solicitudes o Escritos
Las solicitudes o escritos deben estar almacenados en formato PDF. Posteriormente, deberán ser firmados electrónicamente en formato PAdES-LTV.
La Gerencia de Tecnología de Información y Comunicación publicará en el sitio web de la Comisión videos tutoriales, con el procedimiento que los usuarios deben seguir para firmar electrónicamente las solicitudes o escritos.
Firmas Electrónicas Válidas para Firmar Electrónicamente las Solicitudes o Escritos
El SGE únicamente reconocerá como válidas, las siguientes firmas electrónicas:
La firma electrónica de la Comisión, definida en el Artículo 4 de las NORMAS PARA REGULAR LA FIRMA ELECTRÓNICA DE LA COMISIÓN NACIONAL DE BANCOS Y SEGUROS.
La firma electrónica conformada por una firma digital generada a base de un certificado digital, el cual deberá ser emitido por una autoridad certificadora autorizada por la Dirección General de Propiedad Intelectual (DIGEPIH) dependiente del Instituto de la Propiedad.
Cualquier otra firma electrónica que la Comisión resuelva mediante Resolución, de conformidad al marco legal y normativo vigente.

## Guía para uso de firma digital WEB de la CNBS

Descargar Certificados de Confianza

## Circular CNBS No. 018/2019

Resolución GTI No.978/10-12-2019, la Comisión Nacional de Bancos y Seguros Aprobó el “Sistema de Gestiones Electrónicas de la Comisión Nacional de Bancos y Seguros (CNBS)”

## Circular CNBS No. 017/2019

Resolución GTI No.977/10-12-201, la Comisión Nacional de Bancos y Seguros Aprobó Reformar las “Normas Reguladoras de Firmas Electrónicas administradas por la Comisión Nacional de Bancos y Seguros”

## Circular CNBS No.039/2020

RESOLUCIÓN GTI No.452/30-09-2020, por medio de la cual se resuelve comunicar a las Instituciones Supervisadas que toda solicitud o trámites a realizarse ante esta Comisión Nacional de Bancos y Seguros, deberá ser presentado por los canales digitales siguientes: El Sistema de Gestiones Electrónicas (SGE) y la Ventanilla Electrónica de Correspondencia.
Ingresar Ahora

## Otro texto del documento

GUIA DE USUARIO PARA
FIRMA DE DOCUMENTOS
Acrobat Reader
Comisión Nacional de Bancos y Seguros
10/06/2020

## Otro texto del documento — Guia_Configurar_Acrobat_Reader_Firma_Digital.pdf

GUIA PARA CONFIGURAR
ACROBAT READER

Comisión Nacional de Bancos y Seguros
21/02/2019
FIRMA DIGITAL DE DOCUMENTOS
1. Abrir Acrobat Reader seleccionar Edición > Preferencias

2. En la ventana que se desplegará, favor seleccionar la opción de Firmas

1
2
3
3. Una vez seleccionada la opción de Firmas, desplegará la siguiente imagen en la cual
se procederá a configurar cada opción. Seleccionar la primera opción Creación y
aspecto > Más…

4. Una vez seleccionado, desplegará la siguiente imagen y proceder a cambiar las
opciones como se muestra, dar clic en Nuevo

4
5
5. Modificar las opciones como se muestra y clic en Aceptar

6. Clic en Aceptar

6
6
7. Seleccionar la segunda opción Verificación > Más…

8. La siguiente imagen desplegará la información que deberá cambiarse y dar clic en
Aceptar

7
8
9. Seleccionar tercer opción Identidades y certificados de confianza > Más… y verificar
que aparezca la información del certificado del usuario, así como se muestra a
continuación

9

10. Seleccionar última opción Marca de hora del documento > Más…

11. En la pantalla mostrada a continuación dar clic en el icono de servidor

10
11
12. Llenar la siguiente pantalla con la información que se muestra a continuación y dar
clic en Aceptar

Nombre: TSS-CNBS
Dirección URL del servidor: http://tss.cnbs.gob.hn/TSS/HttpTspServer

13. Deberá aparecer el nombre del servidor y el URL agregados, tal como se muestra,
dar clic en la opción Establecer predeterminado

12
13

14. Clic en Aceptar

15. Verificar que aparezca con la

14

## Otro texto del documento — Guia_Emision_Certificado_Para_Firma_Digital.pdf

Infraestructura de Firma
Electrónica de la CNBS
Manual de Emisión de Certificado
Digital por la Autoridad
Certificadora de la CNBS

## Otro texto del documento — 00-Guia-para-uso-de-firma-digital-WEB-de-la-CNBS-V02.pdf

Pasos para uso de firma digital de la CNBS
Luego de Hacer clic en https://esign.cnbs.gob.hn/ :
1. Escribir su correo electrónico y hacer clic en “Siguiente”

2. Escribir clave y código de seguridad solicitado, luego “Ingresar”

3. Escribir código de seguridad que se le envió a su cuenta de correo y “Enviar”

4. Hacer clic en “Seleccionar el archivo” para cargar el archivo que quiere firmar

Nota: considerar que solo se pueden cargar archivos PDF, igualmente su tamaño no pude ser
mayor de 50 MB.

## Documentos

- [Guia_Usuario_Firma_Documento_Acrobat_Reader.pdf](https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Usuario_Firma_Documento_Acrobat_Reader.pdf)
- [Guia_Configurar_Acrobat_Reader_Firma_Digital.pdf](https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Configurar_Acrobat_Reader_Firma_Digital.pdf)
- [Guia_Emision_Certificado_Para_Firma_Digital.pdf](https://www.cnbs.gob.hn/wp-content/uploads/2020/06/Guia_Emision_Certificado_Para_Firma_Digital.pdf)
- [00-Guia-para-uso-de-firma-digital-WEB-de-la-CNBS-V02.pdf](https://www.cnbs.gob.hn/wp-content/uploads/2026/03/00-Guia-para-uso-de-firma-digital-WEB-de-la-CNBS-V02.pdf)

## Fuente

- Ficha: https://www.cnbs.gob.hn/sistema-de-gestiones-electronicas/
- Fecha y hora de extracción: 2026-11-14 00:16 (hora de Honduras, UTC-6)
<!-- portal:fin -->

## Notas propias
