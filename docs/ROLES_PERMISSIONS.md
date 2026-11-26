# Roles y permisos del restaurante

Los roles iniciales conservan sus nombres y alcances. El rol Administrador recibe los nuevos permisos de la fase mediante migración. Las cuentas de plataforma mantienen sus permisos por separado.

Los roles personalizados se editan por módulo y acción. Para delegar, la persona administradora debe poseer todos los permisos efectivos del rol. Los roles iniciales están protegidos. Los roles con gestión de usuarios, invitaciones, sesiones, recuperación, roles o configuración ocupan cupo administrativo. Editar una membresía o un rol recalcula cupos en la misma transacción y conserva al menos un administrador activo.

Las invitaciones pendientes reservan un cupo del tipo de rol durante 24 horas. Vencimiento y cancelación lo liberan automáticamente. Reenviar reemplaza el enlace anterior. Aceptar transforma la reserva en una membresía dentro de una transacción y vuelve a validar los permisos de quien invitó. Las credenciales e identidades son globales y el nombre visible del integrante se edita únicamente para su restaurante. La revocación desde el equipo se limita a sesiones asignadas al restaurante activo.

Los permisos de catálogo, clientes y medios son distintos. Buscar clientes requiere permiso de lectura o gestión. Exportar requiere `customers.export`. Una cuenta con permiso operativo de catálogo puede ver imágenes usadas por ese catálogo. La biblioteca completa requiere `media.manage`.

## Operación del POS

- Mesero · Consulta mesas y pedidos, guarda borradores, administra sus líneas, envía comandas y solicita la cuenta preliminar.
- Cocinero · Consulta comandas y cambia la preparación dentro de sus estaciones permitidas.
- Cajero · Consulta pedidos, divide o reúne cuentas y prepara la solicitud de cobro.
- Administrador · Configura estaciones y límites, asigna meseros, traslada mesas, autoriza descuentos y cancela o ajusta preparaciones.

Los roles personalizados pueden recibir permisos granulares de pedidos, cocina, vistas preliminares e indicadores. El permiso de acceso a todas las estaciones incluye la cola General.
