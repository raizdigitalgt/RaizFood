# Progreso de Raíz Food

## Fase 1 · Fundamentos

- FastAPI, Next.js App Router, TypeScript estricto, Tailwind, Plus Jakarta Sans y componentes Dark POS.
- SQLite persistente en WAL, claves foráneas, aislamiento por membresía y escrituras atómicas para altas y cupos.
- Login por correo, Argon2id, cookies HTTP-only, rotación con detección de reutilización, cierre de sesión y recuperación por enlace emitido desde CLI. TOTP obligatorio para la plataforma en producción.
- Paneles de plataforma y restaurante, selección de membresía, navegación adaptable, registro de establecimientos, consulta de planes, alta y asociación de usuarios.
- Migraciones `0001_foundations` y `0002_platform_mfa`. Entornos de prueba y desarrollo separados.
- Dependencias bloqueadas en `package-lock.json`, `requirements.txt` y `requirements-dev.txt`.

### Verificación local

- Windows con Python 3.14.5, Node.js 24.16.0 y npm 11.13.0.
- Instalación local con el script de PowerShell, aplicación de migraciones y comprobación de coherencia con Alembic. La revisión 0002 se revirtió y reaplicó en una base de prueba.
- Ruff, ESLint, validación de tipos y compilación de Next.js aprobados.
- Pytest sobre SQLite en archivo. 9 pruebas aprobadas, 88.11 % de cobertura total.
- Playwright en Microsoft Edge. Una prueba E2E aprobada con inicio de sesión, alta de restaurante, asociación de usuario y navegación móvil.
- El cliente de pruebas de Starlette emite un aviso de obsolescencia de httpx. La ejecución local pasó.
- GitHub Actions está configurado para Ubuntu y Chromium. La verificación disponible corresponde a Windows local.

## Fase 2 · Superadministrador y gestión comercial

- Navegación de plataforma por permisos. Dashboard y reportes con datos de SQLite, filtros, gráficas y accesos rápidos.
- Directorio filtrado, ficha comercial de restaurantes, usuarios, actividad, observaciones y control de suspensión.
- Catálogo de planes con versiones, contratos históricos, reglas de vigencia y gracia, renovaciones, cobros parciales, recibos de imagen, reversión y exportaciones CSV/PDF.
- Roles y sesiones de plataforma, invitaciones y recuperación por SMTP, personalización, auditoría, notificaciones y seguimiento de soporte.
- Respaldos con manifiesto, descarga autorizada, verificación, retención y restauración de una copia independiente. FEL general muestra elegibilidad; la certificación está prevista para Fase 7.

### Migraciones y verificación

- Copia previa verificada de revisión `0002`, conservada en `backend/.data/backups/` junto con su manifiesto. La copia registrada para la migración es `raizfood-62ecbe93-3fd4-48d7-a6d6-27b237d26555.db`.
- `0003_commercial`, `0004_queued_mail_and_audit` y `0005_onboarding_version` aplicadas primero a una copia y luego a la base local. Alembic, `integrity_check` y `foreign_key_check` aprobaron.
- Pytest en Windows: 17 pruebas aprobadas, 88,19 % de cobertura. Incluye concurrencia de cobros, reutilización de solicitud, revocación, vigencia, restauración independiente y retención.
- Playwright en Edge: 3 pruebas aprobadas. Ruff, ESLint, TypeScript y compilación de Next.js aprobados.
- El cliente de pruebas de Starlette sigue mostrando un aviso de obsolescencia de httpx. La suite también puede emitir un aviso de cierre de conexión durante pruebas con clientes concurrentes.

### Archivos principales

- Backend nuevo en `backend/app/`: modelos y esquemas comerciales, derechos de suscripción, cobros, accesos de plataforma, administración, reportes, imágenes, correo en cola, respaldo y mantenimiento. Se actualizaron autenticación, permisos de restaurantes, configuración y registro de rutas.
- Frontend nuevo en `frontend/components/platform/` y en las rutas de detalle comercial y aceptación de invitaciones. Se actualizó el menú lateral, el login, la recuperación, la marca y los paneles existentes.
- Se agregaron tres migraciones, dos archivos de pruebas de backend, la suite comercial de Playwright y los scripts de mantenimiento. Se actualizaron los bloqueos de dependencias, las guías operativas y el registro de cambios.

### Operación local y alcance

SMTP se verificó con el proveedor simulado. La entrega real requiere credenciales y servidor autorizados. Los respaldos y alertas automáticos se habilitan mediante la política del panel y una tarea del sistema operativo. La restauración verificada se realizó en un archivo independiente. La Fase 3 puede iniciarse sobre esta base local.
