# Corrección local de permisos del contenedor

## Causa raíz

El bootstrap del commit `7ef7b87` descarga el repositorio bajo `umask 077`.
En el despliegue fallido se observaron directorios `0700` y archivos Python
`0600`, propiedad de root. `COPY` conservó esos permisos en la imagen y Uvicorn,
ejecutado como `appuser`, no pudo importar `/app/backend/app/__init__.py`.
El resultado fue `PermissionError`, seguido por fallo de readiness y una señal
FAILURE de `cfn-signal`. PostgreSQL estaba sano.

Las pruebas anteriores construían desde Windows y no reproducían los permisos
del checkout Linux. Esta tarea no volvió a consultar ni modificar AWS: la causa
remota se basa en la evidencia ya recopilada en el despliegue anterior.

## Corrección aplicada

En `Dockerfile`, después de copiar backend y frontend y antes de `USER appuser`:

```dockerfile
RUN chmod -R a+rX /app/backend/app /app/backend/static
```

La operación añade lectura y recorrido de directorios únicamente en los árboles
de código y assets. No cambia el usuario de ejecución, propietario, permisos de
escritura, variables de entorno, `.env`, token del origen ni archivos privados.
La fuente sigue siendo propiedad de root y no puede ser modificada por appuser.
PostgreSQL, CloudFormation y la arquitectura permanecen sin cambios.

## Regresión de comportamiento real

`deploy/aws/tests/test_security.py` genera archivos tar que Docker extrae como
contextos Linux: propietario y grupo root, directorios `0700` y archivos `0600`.
Los metadatos se verifican antes de enviar el contexto. La selección explícita de
archivos excluye `.env`, credenciales, archivos privados de parámetros, caches,
dependencias locales y el `frontend/package-lock.json` preexistente sin seguimiento.

Se construyen dos imágenes temporales con el mismo código/contexto:

- Control negativo: Dockerfile actual sin la línea de corrección; importar
  `app.main` debe fallar con `PermissionError`.
- Imagen corregida: debe ejecutar como appuser no root, importar `app.main` y
  `backend.app.main`, leer archivos y recorrer directorios de app/static, y
  mantener esos árboles sin escritura para el usuario de ejecución.

La imagen corregida se inicia con su CMD real de Uvicorn. Se comprueban HTTP 200
en `/health/ready` y en la página frontend, el usuario efectivo appuser y la
ausencia de PermissionError en los logs.

Las ocho pruebas de integración de origen reutilizan exactamente esa imagen
construida desde el contexto restrictivo, sin volver a construir desde Windows.
Se usan PostgreSQL y Caddy reales en un proyecto Compose local único, con volumen
propio, puertos de loopback aleatorios y credenciales efímeras no impresas.
Se comprueban readiness, frontend, PostgreSQL, login demo deshabilitado en
producción, upgrade WebSocket y autenticación del origen: rechazo de tokens
ausentes/incorrectos, configuración vacía/malformada y retirada de la cabecera
antes del backend.

Los contenedores, volumen e imágenes creados por la prueba se eliminan al acabar.
No se utilizan bases de datos o recursos AWS ni se alteran volúmenes existentes.

## Ejecutar las pruebas

Se requiere Docker local, el entorno Python de validación con PyYAML y el entorno
existente del backend con uv. Desde `deploy/aws/tests`:

```powershell
$env:BLUEPRINT_RUN_DOCKER_TESTS = '1'
python -m unittest -v test_security.RestrictedPermissions test_security.OriginIntegration
Remove-Item Env:BLUEPRINT_RUN_DOCKER_TESTS
```

Desde `backend/`:

```powershell
uv run --locked python -m pytest -q
```

## Resultado de esta revisión

Validación local completada el 30 de octubre de 2026:

| Comprobación | Resultado |
| --- | --- |
| Contextos tar con UID/GID root y modos 0700/0600 | Verificados antes de construir ambas imágenes |
| Control negativo sin la corrección | Reproduce PermissionError al importar app.main |
| Imagen corregida | appuser no root; importaciones app.main y backend.app.main correctas |
| Archivos y directorios app/static | Lectura/recorrido correctos, propiedad root y sin escritura para appuser |
| Arranque real de Uvicorn | Readiness y frontend HTTP 200; logs sin PermissionError |
| Regresión Docker | 3 pruebas aprobadas |
| Integración Compose/PostgreSQL/FastAPI/Caddy | 8 pruebas aprobadas con la misma imagen del contexto restrictivo |
| Autenticación del origen | Rechazo de valores ausentes/incorrectos, configuración inválida, retirada de cabecera y WebSocket aprobados |
| Backend | 20 pruebas aprobadas y 1 integración omitida en esa ejecución; PostgreSQL aprobado por separado dentro de la suite Docker |
| Advertencias del backend | Una deprecación existente de Starlette/AnyIO |

La suite Docker ejecutó las 11 pruebas sin omisiones. Las credenciales efímeras
de integración no se imprimieron. No se tomó la presencia de chmod como prueba
de corrección: se verificaron tanto el fallo anterior como la ejecución real de
la imagen corregida.

Archivos modificados: `Dockerfile`, `deploy/aws/tests/test_security.py` y este
informe. No se cambiaron código del backend, archivos privados, Compose,
CloudFormation, estrategia de almacenamiento ni configuración del origen.
`frontend/package-lock.json` se dejó intacto y fuera del commit.

## Límites pendientes

La corrección y las pruebas son locales. No recuperan el stack CREATE_FAILED ni
modifican su EC2, sus contenedores o sus costes. La imagen corregida no se ha
desplegado en AWS. La recuperación y cualquier operación de infraestructura
requerirán una autorización posterior. No se hace push automático.

Continúan los límites educativos ya documentados: instancia única, PostgreSQL
descartable en disco raíz y HTTP entre CloudFront y el origen. Esta corrección
no amplía el alcance de seguridad o arquitectura.
