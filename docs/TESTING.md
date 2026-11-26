# Pruebas

- Pytest migra una base SQLite temporal por prueba y ejecuta solicitudes contra FastAPI. Cubre configuración SQLite, autenticación, permisos, aislamiento, MFA, renovación de sesión, recuperación, planes, concurrencia y bloqueo.
- Playwright arranca Next.js y FastAPI con un SQLite dedicado y una cuenta ficticia. Valida el alta de restaurante y de usuario, sesión de plataforma, acceso del restaurante y navegación móvil.
- Ruff, ESLint, comprobación de tipos y compilación se ejecutan en los scripts de validación. GitHub Actions configura el entorno Linux y ejecuta la misma secuencia con Chromium.

La Fase 2 añade pruebas de planes históricos, suscripciones, pagos parciales, renovaciones concurrentes, roles, SMTP simulado, invitaciones, actas de auditoría, personalización, copias verificadas y restauración en una base independiente. Las pruebas de navegador cubren el recorrido comercial, SMTP con un proveedor simulado y la modificación del logo. El SMTP real requiere credenciales y un destino autorizado.

Comandos reproducibles en [README.md](../README.md).
