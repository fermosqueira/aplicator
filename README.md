# Aplicador

[![tests](https://github.com/fermosqueira/aplicator/actions/workflows/tests.yml/badge.svg)](https://github.com/fermosqueira/aplicator/actions/workflows/tests.yml)

Convierte los mails que aparecen en las ofertas de LinkedIn en un botón: click, tres campos,
enviado. Y deja registro de a qué empresa y puesto corresponde cada dirección.

## El problema

Buscando trabajo de QA, el feed de LinkedIn se llena de publicaciones con ofertas que piden
enviar el CV a una dirección de mail. El proceso era siempre igual: copiar el mail, abrir
Gmail, mail nuevo, pegar, elegir la plantilla según el idioma, adjuntar el CV, enviar.

Y algo peor que lo tedioso: cuando un recruiter respondía tres semanas después, **no había
forma de saber a qué empresa o puesto correspondía esa casilla**. El envío no quedaba
registrado en ningún lado.

## Cómo funciona

```
Extensión de Chrome  ──chrome.runtime.sendMessage──▶  Service Worker
(detecta los mails, muestra el panel)                       │ fetch
                                                            ▼
                                             Servidor local 127.0.0.1:8765
                                                            │
                                     ┌──────────────────────┼──────────────────────┐
                                     ▼                      ▼                      ▼
                               SMTP (enviar)         IMAP (etiquetar)      SQLite (registrar)
```

El fetch sale del service worker y no del content script: con `host_permissions` declarados
evita por completo el CORS y la CSP de LinkedIn, que es donde se traba la mayoría de las
extensiones que intentan hablar con un proceso local.

**Cero dependencias.** Todo el backend sale de la biblioteca estándar de Python.

### Detalles que resultaron menos obvios de lo esperado

- **Gmail reescribe el `Message-ID`** de lo que sale por su SMTP, así que no sirve para
  reencontrar la copia en Enviados y etiquetarla. Se usa una cabecera propia `X-Aplicador-Id`,
  con búsqueda por destinatario como plan B.
- **La carpeta de enviados se ubica por el flag `\Sent` de IMAP**, no por nombre: una cuenta
  en inglés la llama `[Gmail]/Sent Mail` y una en español `[Gmail]/Enviados`.
- **LinkedIn convierte los mails de los posts en links `mailto:`.** La primera versión los
  ignoraba —evitaba tocar links existentes— y por eso no detectaba nada en el feed real.
- **La detección recorre nodos de texto con una expresión regular, no selectores CSS.**
  LinkedIn genera sus nombres de clase y los rota; un mail escrito en un post, en cambio,
  siempre es un nodo de texto.

## Cómo sabés quién te respondió

Tres capas, de la más liviana a la más completa.

**En la bandeja.** Al enviar, el mensaje queda etiquetado como `Postulaciones/<Empresa>` y el
puesto viaja en el asunto, así que la respuesta llega como `Re: Postulación QA Automation…`
con la empresa a la vista. Una etiqueta por postulación sería inmanejable a los cuarenta
envíos; por eso la empresa va en la etiqueta y el puesto en el asunto.

**El detector.** Recorre las postulaciones pendientes, busca la conversación en Gmail por su
`X-GM-THRID` y, cuando encuentra un mensaje que no es tuyo, marca la postulación como
respondida y **le pone la etiqueta también al mensaje de respuesta**. Buscar por hilo y no por
remitente hace que funcione aunque conteste otra persona de la empresa desde otra dirección
—pasó: una respuesta llegó desde `contacto@` cuando el envío había ido a `contacto+qa@`.

Corre **solo, cada 30 minutos** mientras el servidor está arriba (`revisar_cada_minutos` en
`config.json`; `0` lo apaga). También está el botón `Buscar respuestas` del panel y
`--respuestas` por consola, pero son el atajo, no el mecanismo: algo que hay que acordarse de
disparar, para algo que pasa semanas después, en la práctica no existe.

**El "me dijeron que no".** Lo marcás vos, con un botón en la fila del panel: queda tachada y
en rojo, y sale de las pendientes. Es manual a propósito. Un rebote se reconoce por su
estructura —lo manda un `mailer-daemon`, no hay ambigüedad—, pero un rechazo hay que leerlo, y
"no avanzamos con esta posición, pero tenemos otra" se parece demasiado a un no. Dar por
perdida una postulación que seguía viva es el error caro, así que esa lectura la hace una
persona. Se deshace con el mismo botón.

**Rebotes.** Un mail que rebota vuelve por el mismo hilo y desde una dirección ajena, así que
sin distinguirlo cuenta como respuesta y la postulación queda dada por cerrada cuando en
realidad no llegó a nadie. Los mensajes de `mailer-daemon` y `postmaster` se marcan aparte y el
panel los muestra como **error**, no como respondida; si el dominio se parece a uno conocido,
la fila dice cuál —`@gmail.co` contra `@gmail.com`, que es el caso que costó una postulación
de verdad. Si en el hilo hay un rebote *y* después una respuesta humana, gana la respuesta.

**El post guardado.** Es lo que realmente resuelve el problema. Cuando responden un mes
después, "QA Automation en Trustpeople" no alcanza para recordar de qué oferta se trataba: el
detalle —que el cliente era Mercado Pago, que pedían SQL Server, que era presencial en CDMX—
estaba en la publicación. Se guarda entera, con el autor y el permalink, y el buscador del
panel la encuentra por cualquier palabra que tenga adentro.

## El panel

`http://127.0.0.1:8765/historial`

Buscador arriba, una fila por postulación, y cada fila se despliega mostrando el post
completo, el link a la publicación y el link al hilo de Gmail. El buscador cubre mail,
empresa, puesto, recruiter, autor y **el cuerpo del post**, ignora acentos y mayúsculas, y
exige que estén todos los términos que escribas.

La página la sirve el propio servidor, así que sus pedidos son same-origin y el token puede
viajar embebido sin exponerse a nadie.

## Puesta en marcha

1. **App Password de Gmail.** Requiere verificación en 2 pasos. Se genera en
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
2. `cp config.example.json config.json` y completar: mail, nombre, app password, portfolio,
   y un token para el servidor local (el propio archivo dice cómo generarlo).
3. `cp extension/token.example.js extension/token.js` y pegarle **el mismo token** que
   quedó en `config.json`. Los dos archivos están gitignoreados.
4. Poner los CV en la carpeta con los nombres que figuran en `config.json`.
5. Verificar: `python enviar_cli.py --probar` → tiene que decir `SMTP: OK` e `IMAP: OK`.
6. Cargar la extensión: `chrome://extensions` (o `brave://extensions`) → Modo de
   desarrollador → Cargar descomprimida → carpeta `extension`.

## Uso

El servidor tiene que estar corriendo. Para que arranque solo al iniciar sesión, sin ventana
de consola:

```
powershell -ExecutionPolicy Bypass -File instalar-inicio.ps1
```

Crea un acceso directo en la carpeta de Inicio que lo lanza con `pythonw.exe`. Para apagarlo,
`detener.bat`; para desinstalarlo, el mismo script con `-Quitar`. Como no hay consola, lo que
pasa queda en `servidor.log`. También se puede seguir levantando a mano con `iniciar.bat`.

En LinkedIn los mails aparecen resaltados. Al hacer click se abre un panel a la derecha con la
empresa, el puesto y el idioma ya completados a partir del texto del post.

El panel **no bloquea la página**: se puede seguir scrolleando el feed y leer el post completo.
Además el texto de la publicación viaja dentro del panel, que importa sobre todo cuando el mail
es de una consultora externa y la empresa que contrata solo figura en el cuerpo del post.

El botón pide **dos clicks a propósito**: el primero muestra el mail exacto que va a salir, el
segundo lo manda. Editar cualquier campo invalida el borrador y obliga a mirarlo de nuevo. Un
mail mal dirigido a un recruiter no se puede deshacer.

### Desde la consola

```bash
python enviar_cli.py --probar
python enviar_cli.py --ver rrhh@acme.com --empresa Acme --puesto "QA Automation"
python enviar_cli.py --enviar rrhh@acme.com --empresa Acme --puesto "QA Automation" --recruiter Ana
python enviar_cli.py --historial
python enviar_cli.py --buscar "mercado pago"
python enviar_cli.py --respuestas
```

`--ver` nunca envía nada. `--idioma en` cambia plantilla, CV y el link del portfolio.

## Tests

```bash
cd tests && python -m unittest discover -v
```

79 tests, sin dependencias ni servicios externos. Los fixtures arman su propia carpeta con
plantillas y PDF de mentira, así que corren igual en cualquier máquina y en CI, donde no
existen ni `config.json` ni los CV.

Cubren la detección de idioma, puesto y empresa; el armado del mail (incluida la garantía de
que **nunca** salga un `{placeholder}` sin reemplazar); el saneado de etiquetas para IMAP; el
registro y la detección de duplicados; el buscador; y las dos defensas del servidor local.

Dos que valen la pena mencionar:

- **La migración del esquema.** Una base con el formato viejo tiene que ganar las columnas
  nuevas y conservar sus filas. Si eso falla, alguien pierde su historial por actualizar.
- **El emparejamiento de respuestas**, contra un doble de IMAP. La lógica vive en `nucleo.py`
  y habla contra la interfaz de `correo.Buzon`, que existe justamente para poder probarla sin
  tocar la casilla real.

Ninguna prueba llama a `/enviar` ni a `/respuestas` con un token válido: la primera manda un
mail de verdad y la segunda le escribe etiquetas a Gmail. De las dos solo se verifica que
rechacen a quien no corresponde.

El CI corre además `node --check` sobre el JavaScript de la extensión y falla si alguna vez se
versiona `config.json`, un `.pdf` o la base de datos.

## Estructura

| Archivo | Qué hace |
|---|---|
| `config.json` | Datos, credenciales y rutas. El único que hay que tocar. |
| `(es)/(en) cuerpo mail.txt` | Las plantillas. Los `{huecos}` se completan solos. |
| `plantillas.py` | Arma el texto, detecta idioma, adivina puesto y empresa. |
| `correo.py` | Envía por SMTP y etiqueta por IMAP. |
| `almacen.py` | El registro en SQLite, con el post guardado y el buscador. |
| `nucleo.py` | Orquesta todo. Lo usan la consola y el servidor por igual. |
| `servidor.py` | Le da acceso al motor a la extensión. Solo escucha en `127.0.0.1`. |
| `panel.py` | La página del historial. |
| `extension/` | Manifest V3: content script, panel en Shadow DOM y service worker. |
| `tests/` | La suite. |

## Seguridad

`config.json` guarda el App Password en texto plano y `postulaciones.db` tiene datos de
recruiters: los dos están gitignoreados, junto con los CV.

El servidor local escucha únicamente en `127.0.0.1`, pero eso no alcanza por sí solo:
cualquier página que visites podría intentar hacerle un pedido desde tu propio navegador. Por
eso exige un token propio en cada pedido —una cabecera personalizada obliga al navegador a un
preflight que solo se aprueba para los orígenes de la lista— y verifica el `Origin`. Los tests
cubren las dos defensas.
