# Raíz Food

Plataforma de Raíz Digital para gestionar restaurantes en Guatemala. El panel comercial permite administrar restaurantes, planes versionados, suscripciones y cobros. Los paneles se conectan a FastAPI y SQLite. La gestión de acceso conserva los roles, el aislamiento multitenant y los cupos por restaurante.

## Desarrollo en Windows

Requisitos: Python 3.14, Node.js 24 LTS, npm y PowerShell. Next.js requiere Node.js 20.9 o superior. El conjunto de dependencias se verificó con Node.js 24. [Requisitos de Next.js](https://nextjs.org/docs/app/getting-started/installation)

Desde la raíz:

```powershell
.\scripts\setup.ps1
.\scripts\create-admin.ps1 -Email admin@example.org -Name "Administración"
.\scripts\seed.ps1
```

El script instala las versiones bloqueadas, genera un secreto local al crear `.env`, ejecuta Alembic y siembra los planes. El superadministrador y el seed piden contraseñas sin mostrarlas. El seed es opcional y crea dos restaurantes ficticios. Para abrir el panel de Taquería Central, usa `admin1@taqueria-central.example.org` y la contraseña introducida en el seed. La cuenta inicial de Burger House es `admin1@burger-house.example.org`.

En dos terminales:

```powershell
.\scripts\dev.ps1 backend
```

```powershell
.\scripts\dev.ps1 frontend
```

- Aplicación en [localhost:3000](http://localhost:3000)
- Swagger en [localhost:8000/docs](http://localhost:8000/docs)
- Salud de SQLite en [localhost:8000/api/health](http://localhost:8000/api/health)

Si PowerShell bloquea scripts locales, abre una terminal de sesión con `powershell.exe -NoProfile -ExecutionPolicy RemoteSigned` y ejecuta allí los comandos. Si el alias de Microsoft Store intercepta `python`, pasa el ejecutable de Python 3.14 mediante `-Python`. Usa `localhost` en el navegador para coincidir con el origen configurado.

## Desarrollo en Linux

```bash
bash scripts/setup.sh
(cd backend && .venv/bin/python -m app.cli create-admin --email admin@example.org --name Administración)
(cd backend && .venv/bin/python -m app.cli seed-demo)
bash scripts/dev.sh backend   # Terminal 1
bash scripts/dev.sh frontend  # Terminal 2
```

## Operación comercial

La plataforma puede registrar restaurantes y asignarles usuarios iniciales. Un administrador de restaurante puede consultar y ampliar su equipo dentro del cupo del plan. Para asociar una cuenta existente con otro restaurante, usa la opción del panel de plataforma. Al iniciar sesión con varias membresías aparece el selector.

Para emitir un enlace de recuperación, ejecuta desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.cli reset-link --email usuario@example.org
```

El enlace es de un solo uso y dura 15 minutos. Entrégalo por un canal privado. Tras el cambio se revocan las sesiones de la cuenta. La pantalla de recuperación usa SMTP cuando el servicio está habilitado. El comando de CLI sigue disponible para operación asistida.

El flujo comercial parte de Planes y Restaurantes. En Suscripciones, selecciona el establecimiento, las fechas y el plan. Para renovar, prepara el período siguiente desde el historial. Los pagos confirmados se aplican al período indicado y renuevan cuando cubren el saldo total. La fecha de fin es exclusiva.

Configura `ENCRYPTION_KEY` con una clave de Fernet y `SMTP_ALLOWED_HOSTS` con los servidores SMTP autorizados. Puedes generar la clave desde la raíz con `.\backend\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guárdala en el archivo local `.env` o en el gestor de secretos. Guarda la configuración desde Correo SMTP. Para pruebas locales se admite `SMTP_MODE=mock`, que devuelve el resultado simulado sin contactar a un proveedor. Configura una tarea con `scripts/maintenance.ps1` o `scripts/maintenance.sh` para alertas, cola de correo y respaldos. [Operación de respaldos](docs/BACKUP_RESTORE.md)

## Administración del restaurante

Entra con una cuenta del restaurante para administrar menú, variantes, extras, mesas, clientes, archivos y equipo. El seed local agrega platillos, ilustraciones, salones, mesas y clientes ficticios a los dos restaurantes de demostración. Se puede ejecutar de nuevo sin duplicar registros.

La biblioteca utiliza WebP y guarda las imágenes en el SQLite persistente. Configura `RESTAURANT_IMAGE_MAX_BYTES` para ajustar el límite por imagen. Los archivos se incluyen en los respaldos de SQLite. La revisión de esquema de esta fase es `0006`.

El [catálogo operativo](docs/MENU.md), la [gestión de mesas](docs/TABLES.md), la [biblioteca](docs/MEDIA.md), la [configuración](docs/RESTAURANT_SETTINGS.md) y los [permisos de restaurante](docs/ROLES_PERMISSIONS.md) tienen guías propias.

## Configuración y pruebas

- `.env.example` enumera los parámetros de entorno. SQLite resuelve rutas relativas bajo `backend/`. La configuración local crea `backend/.data/raizfood.db`.
- `FRONTEND_URL` es el origen permitido en solicitudes mutables. `RAIZ_BACKEND_URL` es la dirección interna de FastAPI que usa Next.js al compilar y ejecutar.
- Los precios del seed son configurables en `.env`. Se guardan en centavos y se conservan al repetir el seed.
- `.\scripts\migrate.ps1` ejecuta las migraciones pendientes. La Fase 3 llega a `0006`. Crea y comprueba un respaldo antes de actualizar una base existente. `.\scripts\test.ps1` ejecuta Ruff, Pytest, ESLint, validación de tipos y compilación.
- Para Playwright, ejecuta `npx playwright install chromium` en `frontend` y luego `.\scripts\test.ps1 -Browser` desde la raíz. En Windows puedes usar Edge instalado con `$env:RAIZ_E2E_BROWSER = 'msedge'`. En Linux usa `bash scripts/test.sh --browser`.
- Las pruebas crean bases separadas del entorno de desarrollo.

Consulta [el estado de la entrega](docs/PROGRESS.md), [la arquitectura](docs/ARCHITECTURE.md), [los controles de seguridad](docs/SECURITY.md) y [el plan de implementación](docs/DEVELOPMENT_ROADMAP.md). El agente de impresión, Digifact y el despliegue quedan en las fases indicadas en el plan.
