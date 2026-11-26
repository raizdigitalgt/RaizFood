# Pruebas

- Pytest migra una base SQLite temporal por prueba y ejecuta solicitudes contra FastAPI. Cubre configuración SQLite, autenticación, permisos, aislamiento, MFA, renovación de sesión, recuperación, planes, concurrencia y bloqueo.
- Playwright arranca Next.js y FastAPI con un SQLite dedicado y una cuenta ficticia. Valida el alta de restaurante y de usuario, sesión de plataforma, acceso del restaurante y navegación móvil.
- Ruff, ESLint, comprobación de tipos y compilación se ejecutan en los scripts de validación. GitHub Actions configura el entorno Linux y ejecuta la misma secuencia con Chromium.

La Fase 2 añade pruebas de planes históricos, suscripciones, pagos parciales, renovaciones concurrentes, roles, SMTP simulado, invitaciones, actas de auditoría, personalización, copias verificadas y restauración en una base independiente. Las pruebas de navegador cubren el recorrido comercial, SMTP con un proveedor simulado y la modificación del logo. El SMTP real requiere credenciales y un destino autorizado.

La Fase 3 verifica el CRUD de restaurante, precios, variantes, límites de modificadores, mesas por lote, imagen optimizada, carpetas, permisos de equipo y vigencia de planes. Las pruebas usan dos restaurantes y también verifican restricciones SQL. En Edge se recorren catálogo, multimedia, mesas, equipo, configuración y navegación adaptable.

Comandos reproducibles en [README.md](../README.md).

La Fase 4 agrega `backend/tests/test_pos.py` para pedidos, precios históricos, cocina por estación, transferencias, descuentos, división y combinación, auditoría, aislamiento, WebSocket y concurrencia. `frontend/e2e/pos.spec.ts` recorre la operación con sesiones de mesero, cocinero, administrador y cajero. Verifica entrega de actualizaciones en el navegador, variantes, extras, comandas incrementales, cuenta y recarga móvil. Ejecuta Edge con `$env:RAIZ_E2E_BROWSER = 'msedge'` antes de `./scripts/test.ps1 -Browser`.
