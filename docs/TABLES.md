# Áreas, salones y mesas

Las áreas de atención determinan cómo se agrupan las mesas. Las áreas de preparación se administran de forma independiente y pueden asignarse a platillos. Ambos catálogos permiten marcar áreas inactivas y cambiar su orden.

Crear un lote requiere un área, prefijo, cantidad, primer número y capacidad. El lote de hasta 100 mesas se inserta dentro de una transacción. Si un número ya existe en el área, se revierte todo el lote. El mismo número es válido en otra área.

La administración permite Disponible, En limpieza y Fuera de servicio. El POS marca Ocupada al crear un borrador y Cuenta solicitada al pedir la cuenta. La cancelación libera la mesa. El traslado libera el origen y ocupa el destino dentro de la misma transacción. Cuando hay líneas enviadas se notifican las estaciones.

El tablero operativo consulta `GET /api/restaurants/{slug}/service-tables` y muestra área, capacidad, estado, pedido, total, mesero, preparación y minutos desde la asignación. Los filtros funcionan sobre las áreas del restaurante. La vista se actualiza por WebSocket con consulta periódica de respaldo. El estado Reservada permanece disponible para una futura integración de reservas.
