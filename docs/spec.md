# Por qué documentamos la API

Este repositorio se está organizando para un ejercicio de clase: separar la
aplicación que ve el usuario de un posible backend y dejar por escrito el
acuerdo entre ambos. El contrato técnico está en [`openapi.yaml`](../openapi.yaml).
Este documento explica las decisiones y cómo leerlo.

## Qué hay hoy en el proyecto

| Ubicación | Propósito |
| --- | --- |
| `frontend/` | Aplicación TanStack Start, componentes, pruebas y dependencias de Node.js. |
| `backend/` | Lugar reservado para el backend y sus pruebas. Todavía no contiene una aplicación Python. |
| `docs/` | Explicaciones para quienes desarrollan o revisan el proyecto. |
| `openapi.yaml` | Contrato legible por herramientas: rutas, métodos, datos y autenticación. |
| `AGENTS.md` | Instrucciones de trabajo para agentes que colaboren en el repositorio. |

La separación ayuda a ubicar cada cambio y a mantener independientes las
herramientas de desarrollo: npm pertenece al frontend y `uv` se usaría en un
backend Python. `docs/` conserva el contexto de las decisiones; `AGENTS.md`
indica convenciones de trabajo para que futuras contribuciones sean coherentes.
Ninguna de estas carpetas crea por sí sola una aplicación funcional.

El frontend actual se conecta **directamente a Supabase**. Por eso `openapi.yaml`
describe las llamadas reales a Supabase Auth, PostgREST y las funciones RPC,
además del canal Realtime. No representa un backend Python ya construido ni
propone rutas nuevas como `/api/sessions`. La configuración de datos existente
en `drizzle/` y `supabase/` continúa en la raíz.

## Por qué escribimos el contrato antes del backend

Al leer primero las llamadas del frontend podemos responder con precisión qué
necesita recibir y enviar: por ejemplo, el listado de entrevistas, la creación
de una sesión, el guardado del lienzo y la consulta mediante un enlace de
invitación. El contrato evita que frontend y backend hagan suposiciones distintas
sobre nombres de campos, formatos, métodos o permisos.

También sirve como lista de verificación para implementar y probar el backend.
Si en el ejercicio se reemplaza Supabase por una API propia, habrá que decidir
si esa API conservará estas rutas y respuestas o si se adaptará el cliente del
frontend. En cualquiera de los dos casos, el contrato debe actualizarse junto
con el código; el archivo por sí solo no implementa ni protege una ruta.

## Cómo leer `openapi.yaml`

- `servers` indica el servidor base. La URL de ejemplo se sustituye por
  `VITE_SUPABASE_URL` en el navegador o `SUPABASE_URL` en el servidor.
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
modificar `interview_sessions`. Las políticas de seguridad de filas de la base
de datos restringen esas operaciones al propietario de la sesión.

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

`frontend/` usa Node.js y npm. La indicación de usar `uv` en `AGENTS.md` se
aplicará cuando exista un backend Python: `uv` gestionará sus dependencias y
su entorno de ejecución. Los commits frecuentes de Git sirven para guardar
puntos de avance revisables; un commit local no publica cambios en GitHub.
