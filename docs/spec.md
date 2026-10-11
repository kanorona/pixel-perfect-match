# Por qué documentamos la API

Este repositorio se está organizando para un ejercicio de clase: separar la
aplicación que ve el usuario del backend y dejar por escrito el
acuerdo entre ambos. El contrato técnico está en [`openapi.yaml`](../openapi.yaml).
Este documento explica las decisiones y cómo leerlo.

## Qué hay hoy en el proyecto

| Ubicación | Propósito |
| --- | --- |
| `frontend/` | Aplicación TanStack Start, componentes, pruebas y dependencias de Node.js. |
| `backend/` | Backend FastAPI en Python, con datos en memoria y pruebas. |
| `docs/` | Explicaciones para quienes desarrollan o revisan el proyecto. |
| `openapi.yaml` | Contrato legible por herramientas: rutas, métodos, datos y autenticación. |
| `AGENTS.md` | Instrucciones de trabajo para agentes que colaboren en el repositorio. |

La separación ayuda a ubicar cada cambio y a mantener independientes las
herramientas de desarrollo: npm pertenece al frontend y `uv` al backend Python.
`docs/` conserva el contexto de las decisiones; `AGENTS.md`
indica convenciones de trabajo para que futuras contribuciones sean coherentes.
La estructura por sí sola no hace que los servidores se comuniquen: hay que
configurar la URL de la API y ejecutar ambos procesos.

El frontend nació conectado **directamente a Supabase**, una plataforma que
combina PostgreSQL con autenticación, API y comunicación en tiempo real. Por
eso `openapi.yaml` describe las rutas que usa su cliente JavaScript: Auth,
PostgREST, funciones RPC y Realtime. El backend FastAPI local reproduce esas
rutas y formatos con datos en memoria; así el frontend puede cambiar de servidor
mediante `frontend/.env.local`, sin reescribir sus llamadas. La configuración
original de datos en `drizzle/` y `supabase/` continúa en la raíz.

## Por qué escribimos el contrato antes del backend

Al leer primero las llamadas del frontend podemos responder con precisión qué
necesita recibir y enviar: por ejemplo, el listado de entrevistas, la creación
de una sesión, el guardado del lienzo y la consulta mediante un enlace de
invitación. El contrato evita que frontend y backend hagan suposiciones distintas
sobre nombres de campos, formatos, métodos o permisos.

También sirve como lista de verificación para implementar y probar el backend.
En este ejercicio, FastAPI conserva las rutas y respuestas que espera el
frontend. Primero usamos datos en memoria para verificar esa conexión; después
se puede añadir persistencia sin cambiar el acuerdo de la API. El contrato debe
actualizarse junto con el código: el archivo por sí solo no implementa ni
protege una ruta.

## Cómo leer `openapi.yaml`

- `servers` indica los servidores posibles. En localhost se usa FastAPI en
  `127.0.0.1:8001`; `VITE_SUPABASE_URL` elige esa URL en el navegador.
- `paths` reúne cada ruta HTTP con su método, parámetros, cuerpo de solicitud y
  posibles respuestas. Un mismo recurso puede tener `GET`, `POST`, `PATCH` y
  `DELETE`.
- `components.schemas` define estructuras reutilizables, como `Session`,
  `CandidateSession` y `Canvas`, para no repetir los campos en cada operación.
- `security` distingue la clave pública `apikey` del token de acceso del
  entrevistador. La clave pública identifica el proyecto; **no demuestra que
  alguien haya iniciado sesión**.

### Dos formas de acceder a una entrevista

El entrevistador inicia sesión y envía su token de usuario al consultar o
modificar `interview_sessions`. Supabase usa políticas de seguridad de filas;
el backend en memoria comprueba la propiedad de cada entrevista antes de
leerla o modificarla.

El candidato no crea una cuenta: recibe un enlace con un token secreto. El
frontend lo envía a `get_session_by_token` para leer la sesión y a
`save_canvas_by_token` para guardar el lienzo. Esa segunda función solo guarda
cuando la entrevista está en estado `live` y la edición no está bloqueada.
El token del enlace debe tratarse como una credencial, aunque viaje en el
cuerpo de la solicitud en vez de la cabecera `Authorization`.

## Qué cambia con Realtime

El lienzo compartido usa un WebSocket para presencia, cursores y cambios
instantáneos. OpenAPI describe principalmente HTTP, así que la ruta WebSocket
tiene una extensión `x-realtime` que enumera los eventos (`op`, `sync-req`,
`sync`, `cursor` y `session`). Los cambios también se guardan por HTTP; recibir
un evento en vivo no equivale a persistirlo.

Hay una limitación importante en el código actual: el candidato se une al
canal público `room:<sessionId>` sin enviar el token de invitación en esa
suscripción. El contrato lo señala para que no se confunda el acceso al canal
con la validación del enlace. Si se implementa un backend nuevo, habrá que
definir explícitamente cómo se autoriza la comunicación en tiempo real.

## Herramientas de trabajo

`frontend/` usa Node.js y npm. El backend Python usa `uv` para gestionar sus
dependencias y su entorno de ejecución. Los commits frecuentes de Git sirven para guardar
puntos de avance revisables; un commit local no publica cambios en GitHub.
