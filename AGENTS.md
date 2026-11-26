# Raíz Food

Monolito modular con Next.js, FastAPI y SQLite. Trabajar por fases y actualizar docs/PROGRESS.md con verificaciones reales.

- Derivar el tenant de la sesión autenticada, validar membresía y permisos en cada operación y filtrar consultas por tenant.
- Usar claves foráneas compuestas entre recursos de un mismo restaurante. Probar con al menos dos restaurantes.
- Mantener SQLite local en WAL, escrituras breves y transacciones atómicas. Revisar los invariantes de cupo y cobro bajo concurrencia.
- Usar UUID, fechas UTC, centavos enteros y unidades base para existencias.
- Mantener credenciales y datos locales fuera de Git. Los datos de demostración se admiten solo en desarrollo.
- Verificar migraciones, lint, tipos y pruebas antes de cerrar una fase. Crear un respaldo verificable antes de aplicar migraciones a una base existente.
- Mantener versiones de planes inmutables. Aplicar y revertir cobros y renovaciones bajo una escritura reservada. Procesar SMTP y generación de archivos fuera de la transacción.
- Requerir autorización para despliegues públicos y certificaciones fiscales reales.
