# Raíz Food

Monolito modular con Next.js, FastAPI y SQLite. Trabajar por fases y actualizar docs/PROGRESS.md con verificaciones reales.

- Derivar el tenant de la sesión autenticada, validar membresía y permisos en cada operación y filtrar consultas por tenant.
- Usar claves foráneas compuestas entre recursos de un mismo restaurante. Probar con al menos dos restaurantes.
- Mantener SQLite local en WAL, escrituras breves y transacciones atómicas. Revisar los invariantes de cupo y cobro bajo concurrencia.
- Usar UUID, fechas UTC, centavos enteros y unidades base para existencias.
- Mantener credenciales y datos locales fuera de Git. Los datos de demostración se admiten solo en desarrollo.
- Verificar migraciones, lint, tipos y pruebas antes de cerrar una fase. Crear un respaldo verificable antes de aplicar migraciones a una base existente.
- Mantener versiones de planes inmutables. Aplicar y revertir cobros y renovaciones bajo una escritura reservada. Procesar SMTP y generación de archivos fuera de la transacción.
- Mantener los precios, cotizaciones y disponibilidades del catálogo bajo reglas de servidor. Las reservas de invitaciones cuentan para los cupos de la versión contratada.
- Requerir autorización para despliegues públicos y certificaciones fiscales reales.
- Validar versión y clave de idempotencia en las acciones del POS. Crear el pedido, actualizar ocupación, generar comandas y guardar auditoría en la transacción que protege cada operación.
- Conservar importes históricos, cantidades y centavos asignados en cuentas divididas. Usar las estaciones autorizadas para consultas y notificaciones de cocina. Reservar estados financieros definitivos para la Fase 7.
