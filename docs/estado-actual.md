# Punto de continuación

Este proyecto es un ejercicio de clase. El frontend en `frontend/` usa el SDK
de Supabase, y el backend FastAPI en `backend/` reproduce las rutas que ese SDK
necesita. La especificación está en `openapi.yaml`; `docs/spec.md` explica las
decisiones. El backend usa SQLAlchemy y guarda los datos por defecto en el
archivo SQLite `backend/blueprint.db`; las sesiones sobreviven al reinicio.

## Estado confirmado

- `frontend/.env.development` dirige el cliente al backend local en
  `http://127.0.0.1:8001` con la clave pública de demostración.
- La compilación `npm run build` terminó correctamente tras conectar el
  frontend, y Vite cargó la URL local de desarrollo.
- En una ejecución anterior, la prueba del frontend pasó. La suite del backend
  pasó completa (7 pruebas) fuera del aislamiento que bloqueaba `TestClient`.
  Falta repetir la prueba completa en navegador después de corregir el canal
  Realtime que aparecía como `Offline` en las capturas del usuario. El SDK
  añadía el prefijo `realtime:` y enviaba las difusiones como tramas binarias;
  el backend ahora admite ambos comportamientos.
- La cuenta de demostración es `demo@example.com` / `DemoPass123!`.

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

Verificar con ambos servidores encendidos el inicio de sesión, la lista de dos
entrevistas de ejemplo, la creación y edición de una sesión, el enlace de
candidato y la sincronización del lienzo entre dos ventanas. El backend ya
acepta el prefijo `realtime:` que añade el SDK al nombre del canal. Si una llamada
falla, comparar su URL, cuerpo y respuesta con `openapi.yaml` y corregir el
cliente o el backend. `frontend/.env.local`, si existe, prevalece sobre la
configuración de desarrollo; comprobar que apunta al puerto 8001.

Al guardar este punto, `frontend/package-lock.json` era un archivo nuevo sin
seguimiento de Git, producido por `npm install`. Revisarlo antes de decidir si
se versiona; no descartarlo sin comprobar si contiene cambios del usuario.
