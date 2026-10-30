# Informe de correcciones previas al despliegue

Fecha: 29 de octubre de 2026. Perfil previsto: `blueprint-dev`.
Región prevista: `us-east-2`. Base publicada: `d00e566`.

## Alcance y restricciones

Se corrigieron archivos locales. No se creó, ejecutó, actualizó ni eliminó ningún
recurso, stack o change set AWS. La única operación de AWS de esta tarea fue
`cloudformation validate-template`, que valida la sintaxis y no despliega.
No se ejecutó `deploy.ps1` ni se hizo push. El change set anterior sigue sin
autorización y representa código anterior a estas correcciones; no debe ejecutarse.

La estrategia de PostgreSQL sigue siendo un volumen Docker sobre el disco raíz
EC2 cifrado de 20 GiB, con eliminación al terminar la instancia. La pérdida de
esos datos es una decisión explícita para esta demostración. No se añadió RDS,
Secrets Manager, un balanceador ni ningún otro servicio o recurso AWS.
`frontend/package-lock.json`, que ya estaba sin seguimiento, quedó intacto.

## Archivos modificados y motivo

| Archivo | Corrección |
| --- | --- |
| `backend/app/store.py` | Seeding deshabilitado por defecto; exige entorno development y activación explícita. Rechaza activación fuera de desarrollo antes de conectar a la base. Añade consulta de disponibilidad. |
| `backend/app/main.py` | `/health/ready` verifica la base y devuelve 503 genérico cuando falla, sin detalles privados. |
| `backend/tests/conftest.py` | Las pruebas que necesitan datos demo los activan expresamente. |
| `backend/tests/test_deployment_security.py` | Comprueba defaults seguros, rechazo de configuraciones incorrectas, registro normal y errores de disponibilidad sin filtración. |
| `Dockerfile` | Defaults de ejecución production y seeding deshabilitado. |
| `Makefile` | El arranque local activa explícitamente las dos opciones de desarrollo. |
| `docker-compose.yaml` | Desarrollo explícito, puertos limitados a loopback y healthcheck de base/API. |
| `docker-compose.aws.yaml` | Fuerza producción sin demo, exige token de origen y usa readiness de base/API. |
| `deploy/aws/Caddyfile` | Verifica el token de origen en todas las rutas; deniega tokens ausentes/incorrectos y configuración vacía/malformada; elimina la cabecera antes del backend; desactiva admin API. |
| `deploy/aws/blueprint-stack.yaml` | Parámetro privado sin default, cabecera en CloudFront, CreationPolicy, manejo de señales/errores, tiempos máximos, reintentos y dependencias de red. |
| `deploy/aws/deploy.ps1` | Ahora prepara solo una propuesta CREATE; no despliega ni ejecuta. Parámetros privados mediante archivo externo, región explícita y SHA completo. |
| `deploy/aws/tests/test_security.py` | Harness de señales y sintaxis Bash, más pruebas reales aisladas de Compose, origen, WebSocket y PostgreSQL. |
| `.gitignore`, `.dockerignore` | Excluyen `.env` raíz y archivos privados de parámetros de Git y del contexto de construcción. |
| `backend/README.md` | Documenta activación local y defaults de producción. |
| `docs/deployment-aws.md` | Procedimiento nuevo, manejo de secretos, límites, rotación y preparación futura de un change set. |
| `docs/predeployment-review.md` | Este informe y sus evidencias. |

## Funcionamiento de las correcciones

### Credenciales demo

El valor predeterminado es `BLUEPRINT_SEED_DEMO=false`. Para crear los usuarios e
interviews de ejemplo se requieren **ambos** `BLUEPRINT_ENV=development` y
`BLUEPRINT_SEED_DEMO=true`. La producción no permite ese opt-in; una configuración
incompatible detiene el proceso. En una base nueva, los usuarios se registran
normalmente mediante la interfaz. No se borran cuentas preexistentes ni se cambia
el almacenamiento. No se generaron ni incorporaron secretos de despliegue al repositorio.

### Arranque confirmado

La EC2 espera la ruta a Internet y la asociación de tabla de rutas. Usa su IP
pública inicial para las descargas; la Elastic IP se asocia después de la señal,
evitando una dependencia circular con la creación de la propia instancia.

CreationPolicy espera una señal durante 30 minutos. El trabajo está limitado a
24 minutos, con reintentos y límites por operación. La señal de éxito requiere
PostgreSQL disponible, consulta real a la base a través de FastAPI/Caddy, página
frontend accesible y rechazo de solicitudes sin autenticación del origen.
El manejador EXIT conserva el código de fallo o timeout y reintenta la entrega
de la señal hasta cinco veces. La falta del helper o de comunicación deja fallar
la creación por timeout en vez de producir un éxito falso.

### Autenticación del origen

Se conserva el security group limitado a la prefix list de CloudFront. Se añade
un secreto compartido aleatorio de 256 bits mediante `OriginVerifyToken`, parámetro
`NoEcho` sin default. CloudFront añade la cabecera y Caddy la exige. El backend
no recibe ese secreto. El token se suministrará fuera de Git en una futura
preparación autorizada; no se generó un token de producción en esta tarea.

La solución usa el [patrón de cabecera personalizada de AWS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html)
con comprobación en Caddy y sin recursos adicionales. La comparación también
rechaza una configuración de servidor vacía o malformada, aunque se eluda Compose.
Las comprobaciones de bootstrap leen la cabecera desde un archivo privado de curl
en vez de incluir el valor en argumentos de proceso. No hay trazas de shell ni
volcados automáticos de configuración o logs de contenedores.

## Validaciones y resultados

| Validación | Resultado final |
| --- | --- |
| AWS `validate-template`, perfil y región indicados | Aceptada; `OriginVerifyToken` marcado `NoEcho`; requiere `CAPABILITY_IAM`. |
| `cfn-lint 1.59.0`, región us-east-2 | 0 errores y 0 advertencias. |
| Backend con `uv` | 20 pruebas aprobadas; una integración PostgreSQL omitida en esa ejecución y aprobada por separado dentro de la suite Docker. Una advertencia de deprecación existente de Starlette/AnyIO. |
| Harness de señales | Éxito, fallo, timeout, reintentos y entrega agotada aprobados. Sintaxis de UserData comprobada con Bash. |
| Docker/Compose real | Ocho pruebas aprobadas: ausencia/token incorrecto; configuración ausente; configuración vacía/malformada de Caddy; cabecera retirada antes del upstream; frontend/readiness; demo rechazado en producción; upgrade WebSocket; integración backend/PostgreSQL. |
| PowerShell | Script parseado sin errores; no ejecutado. |
| CloudFormation Guard 3.2.1 | 24 archivos PASS, 11 FAIL y 18 SKIP; son los mismos avisos de la revisión anterior, sin supresiones nuevas. |
| Limpieza local | Sin contenedores ni volúmenes del proyecto temporal de pruebas después de la suite. |

Las pruebas usaron credenciales efímeras de prueba, sin imprimir sus valores.
Docker construyó la imagen y arrancó un proyecto único con base propia y puertos
aleatorios en loopback. Se limpiaron exclusivamente esos recursos locales.

Las primeras ejecuciones encontraron restricciones del entorno aislado sobre
temporales; la suite del backend se completó fuera de ese aislamiento. Se corrigió
también la captura UTF-8 de logs y una comilla del fixture temporal de Caddy antes
del resultado final aprobado. No se ocultaron fallos del producto mediante skips.

### Avisos de Guard que permanecen

No se declara cumplimiento total. Las reglas restantes exigen:

- `EBS_OPTIMIZED_INSTANCE`: propiedad explícita; T3 ya la ofrece por defecto.
- `EC2_INSTANCE_DETAILED_MONITORING_ENABLED`: monitoreo detallado, con coste adicional.
- `NO_UNRESTRICTED_ROUTE_TO_IGW`, `SUBNET_AUTO_ASSIGN_PUBLIC_IP_DISABLED`: arquitectura
  privada incompatible con el bootstrap público actual sin rediseño.
- `SECURITY_GROUP_MISSING_EGRESS_RULE`: el egress sigue siendo el implícito, abierto.
- `CLOUDFRONT_ACCESSLOGS_ENABLED`: no se añadieron logs de acceso.
- `CLOUDFRONT_CUSTOM_SSL_CERTIFICATE`, `CLOUDFRONT_MINIMUM_PROTOCOL_VERSION_RULE`,
  `CLOUDFRONT_SNI_ENABLED`: el dominio/certificado predeterminado no satisface esas
  reglas. No basta con añadir MinimumProtocolVersion a ese certificado.
- `CLOUDFRONT_DEFAULT_ROOT_OBJECT_CONFIGURED`: el backend dinámico sirve `/`.
- `CLOUDFRONT_ORIGIN_FAILOVER_ENABLED`: no existe un segundo origen.

## Límites y riesgos pendientes

1. CloudFront → EC2 sigue usando HTTP: no cifra el token y no evita su repetición
   si se filtra. Viewer → CloudFront sí usa HTTPS. Solo datos educativos no sensibles.
2. `NoEcho` no protege todas las ubicaciones: personas con permisos para leer
   UserData, la configuración del origen de CloudFront o root/Docker pueden
   recuperar el valor. Restringir esos permisos y proteger el archivo de parámetros.
3. Secreto compartido: su rotación exige coordinar CloudFront y Caddy. Actualizar
   el parámetro no vuelve a ejecutar UserData ni rota el host por sí solo.
4. CreationPolicy comprueba la primera creación. No prueba el dominio público
   todavía inexistente, no sustituye monitoreo continuo y no garantiza updates.
5. No se ha ejecutado EC2: quedan sin comprobar el paquete helper en la AMI real,
   IMDSv2 y verificación de pertenencia del helper, señal en CloudFormation,
   permisos efectivos/SCP, capacidad, red pública, asociación EIP y propagación HTTPS.
6. Continúan la instancia única, datos descartables, ausencia de backups/logs
   durables y versiones móviles en algunas dependencias. El registro de usuarios
   permanece abierto, sin verificación de email ni límites de abuso.
7. Deshabilitar seeding no borra usuarios de una base existente. La prueba pública
   debe partir de una base nueva y no copiar una base de desarrollo.

## Cambios requeridos y siguiente paso

CloudFormation debe recibir la plantilla corregida, el parámetro privado nuevo,
la CreationPolicy/dependencias y un SHA publicado que incluya estos cambios.
Siguen siendo 14 recursos; no cambian la política de borrado del disco ni el
tamaño/tipo propuestos. El change set existente no contiene estas correcciones.

Las [instrucciones de preparación futura](deployment-aws.md#preparing-a-replacement-later--not-done-yet)
explican cómo publicar manualmente el commit revisado, generar el archivo privado
fuera de Git y preparar otra propuesta CREATE con `blueprint-dev`/`us-east-2`.
Requiere una autorización posterior; **no se preparó ni ejecutó esa propuesta**.
