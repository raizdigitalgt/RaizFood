# Actualizaciones en tiempo real

El navegador abre `/api/restaurants/{slug}/events` a través del mismo origen. El proxy debe admitir la actualización de protocolo a WebSocket. Configura `FRONTEND_URL` con el origen y usa HTTPS/WSS en producción.

El servidor valida origen, cookie, sesión, restaurante activo, acceso por suscripción y permisos. Revalida la sesión y las estaciones antes de leer el siguiente lote de eventos. El canal se cierra cuando deja de estar autorizado.

El saludo es `{"type":"sync","events":[]}`. Cada mensaje posterior usa `{"type":"changed","events":[...]}`. Los tipos incluyen cambios `order.*`, `table.updated`, `kitchen_ticket.created`, `kitchen_ticket.updated`, `kitchen_ticket.cancelled`, `menu.availability_changed` y `pos.settings_changed`. Las notificaciones llevan nombres de evento y el contexto del restaurante se toma de la sesión.

La auditoría SQLite se escribe en la misma transacción que el cambio operativo. El canal lee los registros ya confirmados en lotes con un cursor por conexión. El navegador invalida las consultas REST relacionadas. La reconexión usa retraso creciente y vuelve a consultar el estado del módulo. Si el canal se desconecta, las consultas periódicas continúan cada cinco segundos.
