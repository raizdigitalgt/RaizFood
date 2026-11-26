# API de Raíz Food

El navegador usa `/api` del mismo origen. FastAPI publica OpenAPI en `/openapi.json` y Swagger en `/docs` en entornos de desarrollo o pruebas. Los clientes manuales deben enviar en operaciones mutables el encabezado `Origin` que coincide con `FRONTEND_URL` y conservar las cookies de sesión.

| Método y ruta | Operación |
| --- | --- |
| GET /api/health | Estado de la base y modo de diario |
| POST /api/auth/login | Autenticar por correo y contraseña |
| GET /api/auth/me | Identidad, membresías y permisos en el contexto actual |
| POST /api/auth/tenant | Seleccionar una membresía activa |
| POST /api/auth/refresh | Rotar credenciales |
| POST /api/auth/logout | Revocar la sesión |
| POST /api/auth/reset | Cambiar contraseña con un enlace de un solo uso |
| GET /api/platform/dashboard | Resumen y altas recientes |
| GET /api/platform/plans | Precios y cupos iniciales |
| GET, POST /api/platform/restaurants | Buscar, paginar y registrar restaurantes |
| POST /api/platform/restaurants/{slug}/members | Crear o asociar un miembro |
| GET /api/restaurants/{slug}/dashboard | Resumen del restaurante y cupos |
| GET, POST /api/restaurants/{slug}/members | Consultar el equipo y registrar usuarios nuevos |

La API devuelve 401 para sesiones inválidas, 403 para permisos insuficientes, 404 para recursos ausentes en el alcance autorizado, 409 para duplicados o límites y 503 con `Retry-After` cuando SQLite está ocupado.

## API comercial

Las operaciones de plataforma verifican permisos por módulo. Cada módulo se documenta en OpenAPI. Rutas principales de Fase 2 bajo `/api/platform`:

| Recurso | Rutas y alcance |
| --- | --- |
| Catálogo | `GET /plan-catalog`, `POST /plans`, `PUT, DELETE /plans/{code}`, `GET /plans/{code}/versions` |
| Restaurantes | `GET, PUT /restaurants/{slug}`, `POST /restaurants/{slug}/active`, vistas de historial, equipo e invitaciones |
| Contratos | `GET, POST /subscriptions`, `GET /subscriptions/{id}`, cambios de plan, `PUT /subscriptions/{id}/terms`, vigencia y renovaciones |
| Pagos | `GET, POST /payments`, `POST /payments/{id}/state`, descarga de comprobante y `GET /payments-export/{format}` |
| Usuarios | `GET, POST /users`, actualización de cuentas, permisos, sesiones, revocación e invitaciones |
| Plataforma | `GET /commercial-summary`, `GET /reports`, `GET /audit`, `GET /fel`, `GET /security` |
| Configuración | `GET, PUT /settings`, `GET, PUT /smtp`, `POST /smtp/test`, actualizaciones de marca e imágenes |
| Respaldo | `GET, POST /backups`, `PUT /backups/settings`, verificación y descarga de manifiesto o SQLite |
| Seguimiento | `GET /notifications`, lectura individual, alta y actualización de solicitudes en `/support` |

Las rutas públicas nuevas son `GET /api/branding`, `GET /api/branding/assets/{key}`, `POST /api/auth/recover` y `POST /api/auth/invitations/accept`. La descarga de respaldos requiere `backups.download`.
