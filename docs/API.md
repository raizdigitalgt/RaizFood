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

## API de administración y preparación del POS

Las rutas usan el prefijo `/api/restaurants/{slug}`. El servidor valida el *slug* contra la sesión activa y aplica los permisos de plan y rol. Para solicitudes con efectos se requiere el encabezado `Origin` configurado.

| Ruta | Función |
| --- | --- |
| `GET /overview`, `GET /audit` | Indicadores, actividad y auditoría del restaurante |
| `GET, POST /records/{resource}`, `GET, PUT, DELETE /records/{resource}/{id}` | Catálogos, clientes, áreas, mesas, medios y métodos de pago con validación por recurso |
| `POST /tables/batch`, `GET /catalog/tables` | Alta atómica de mesas y lista de mesas de áreas activas |
| `GET /catalog`, `POST /catalog/{id}/quote` | Catálogo, disponibilidad, configuración operativa y cálculo entero de cotizaciones |
| `POST /items/{id}/duplicate`, `GET /items/{id}/prices` | Duplicación e historial de precios |
| `GET /customers/export` | Exportación CSV de clientes bajo permiso específico |
| `POST /media/files`, `GET /media/limits`, `GET /media/files/{id}/content` | Carga, límites y lectura autorizada de imágenes |
| `GET, PUT /settings`, `GET /appearance`, `GET /editor-defaults` | Ajustes administrativos, identidad visible y preferencias iniciales |
| `GET /staff`, `PUT /staff/{id}`, `GET, POST /roles`, `PUT /roles/{code}` | Equipo y permisos personalizados |
| `GET, POST /staff-invitations`, `POST /staff-invitations/cancel` | Invitaciones con reserva de cupo |
| `GET /subscription`, `POST /subscription/requests`, `DELETE /subscription/requests/{id}` | Historial del contrato y solicitudes de cambio |

Los recursos disponibles son `categories`, `items`, `variants`, `groups`, `modifiers`, `areas`, `preparation`, `tables`, `customers`, `folders`, `files` y `payment-methods`. Las listas admiten búsqueda y paginación. Los filtros específicos incluyen estados, área, categoría, platillo, grupo o carpeta. La carga de archivos valida el objeto `name`, `folder_id` y `content` codificado en Base64.

Para cotizar se envían `quantity`, `variant_id` opcional y `modifier_ids`. La respuesta incluye el costo unitario, el costo de extras y el total en centavos. La operación es de solo lectura y prepara el POS.
