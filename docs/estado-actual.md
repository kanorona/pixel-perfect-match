# Punto de continuación

Este proyecto es un ejercicio de clase. El frontend en `frontend/` usa el SDK
de Supabase, y el backend FastAPI en `backend/` reproduce las rutas que ese SDK
necesita. La especificación está en `openapi.yaml`; `docs/spec.md` explica las
decisiones. El backend usa SQLAlchemy y admite SQLite y PostgreSQL. SQLite sigue
siendo el valor por defecto; la aplicación que está ejecutándose actualmente usa
PostgreSQL en Docker.

## Estado confirmado

- `frontend/.env.development` dirige el cliente al backend local en
  `http://127.0.0.1:8001` con la clave pública de demostración.
- La compilación `npm run build` terminó correctamente tras conectar el
  frontend, y Vite cargó la URL local de desarrollo.
- En una ejecución anterior, la prueba del frontend pasó. La suite del backend
  pasó completa (8 pruebas) el 11 de octubre de 2026, incluida una prueba de
  reinicio que conserva cuenta, entrevista, lienzo y tokens, y mantiene borrada
  una entrevista de ejemplo. Falta repetir la prueba completa en navegador
  después de corregir el canal Realtime que aparecía como `Offline` en las
  capturas del usuario. El SDK
  añadía el prefijo `realtime:` y enviaba las difusiones como tramas binarias;
  el backend ahora admite ambos comportamientos.
- La cuenta de demostración es `demo@example.com` / `DemoPass123!`.
- La persistencia con SQLAlchemy y SQLite quedó en el commit `232254a`.
  `BLUEPRINT_DATABASE_URL` permite elegir la base de datos; si no se define,
  el backend usa `backend/blueprint.db`. Los datos nuevos sobreviven al reinicio.
  Los datos que solo existían en la memoria del servidor anterior no se pueden
  recuperar.
- El soporte PostgreSQL quedó en el commit `bfcaaef`. Incluye `psycopg`, acepta
  URLs `postgresql://`, prueba autenticación y CRUD contra PostgreSQL, y corrige
  el orden de la carga inicial para respetar la clave foránea del propietario.
- El 28 de octubre de 2026 pasaron 12 pruebas, incluida la integración real con
  PostgreSQL después de reiniciar su contenedor.
- `interview-canvas-db` ejecuta `postgres:16-alpine`. Usa el volumen persistente
  `interview-canvas-pgdata` y publica el puerto 5433 porque un PostgreSQL de
  Windows ya ocupa el 5432.
- `blueprint` ejecuta la imagen reconstruida `blueprint:latest` en el puerto
  8001 y se conecta a `postgresql://sdip:sdip@host.docker.internal:5433/sdip`.
  Se comprobó una escritura desde la API directamente con `psql` y después se
  eliminó el registro temporal.

## Arranque en Windows PowerShell

Terminal 1:

```powershell
cd "D:\AI Dev Tools\pixel-perfect-match\backend"
python -m uv sync
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Terminal 2:

```powershell
cd "D:\AI Dev Tools\pixel-perfect-match\frontend"
npm install
npm run dev -- --host 127.0.0.1 --port 8081
```

Abrir `http://127.0.0.1:8081/`. También existe un `Makefile` con `make setup`,
`make backend` y `make frontend`, pero GNU Make no estaba instalado en Windows
al hacer este punto de continuación. `uv` funciona como `python -m uv`, aunque
el comando `uv` no estaba en el `PATH` de PowerShell.

## Primer paso al retomar

Abrir `http://127.0.0.1:8001/` y verificar el inicio de sesión, la lista de
entrevistas, la creación y edición de una sesión, el enlace de candidato y la
sincronización del lienzo entre dos ventanas. El backend ya
acepta el prefijo `realtime:` que añade el SDK al nombre del canal. Si una llamada
falla, comparar su URL, cuerpo y respuesta con `openapi.yaml` y corregir el
cliente o el backend. `frontend/.env.local`, si existe, prevalece sobre la
configuración de desarrollo; comprobar que apunta al puerto 8001.

La primera vez con una base nueva aparecerán dos entrevistas de ejemplo. En
arranques posteriores se conserva el estado guardado, por lo que el número de
entrevistas puede ser distinto. Para comprobar la persistencia manualmente,
crear una entrevista, reiniciar solo el backend y confirmar que sigue visible.

Al guardar este punto, `frontend/package-lock.json` era un archivo nuevo sin
seguimiento de Git, producido por `npm install`. Revisarlo antes de decidir si
se versiona; no descartarlo sin comprobar si contiene cambios del usuario.
