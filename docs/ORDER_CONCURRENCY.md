# Concurrencia de pedidos

SQLite usa WAL, claves foráneas y `BEGIN IMMEDIATE` para escrituras operativas. Se reserva la escritura antes de consultar la versión o validar el estado de una mesa. Un índice único parcial refuerza el límite de un pedido abierto por mesa. Los correlativos se incrementan transaccionalmente por tenant y tipo de documento.

Al crear un pedido envía `request_id` con un UUID. Las acciones de pedido y cocina requieren también la última `version`. El servidor responde 409 a cambios obsoletos. Consulta el estado real y confirma la acción con la versión nueva antes de reintentar una edición en conflicto.

Un reintento de la misma acción conserva UUID, versión y cuerpo. SQLite guarda huella y respuesta bajo restaurante, autor y UUID. Recibir una solicitud idéntica restaura la respuesta confirmada. Reutilizar el UUID con otro cuerpo o destino devuelve 409. Un fallo que revierte la operación también revierte el registro de idempotencia. El POS reintenta un error de transporte una vez con el mismo cuerpo.

Las divisiones conservan unidades y centavos, los envíos generan tickets solo para líneas nuevas y cada transición del KDS valida la versión del pedido. Las notificaciones pasan por la auditoría ya confirmada.
