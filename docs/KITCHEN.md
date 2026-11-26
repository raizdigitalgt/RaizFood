# Pantalla de cocina

Cada restaurante define sus áreas de preparación. Desde **Configuración → Operación → Configurar punto de venta**, el administrador puede asignar estaciones al personal de cocina. El permiso `kitchen.all_areas` otorga visibilidad de todas, incluida la cola General. Cocina solo puede abrir tickets de una estación autorizada.

El primer envío genera una comanda independiente por estación. El correlativo de cocina es independiente del correlativo de pedidos. Los envíos siguientes toman únicamente líneas nuevas. El envío repetido sin líneas nuevas devuelve una lista vacía.

El KDS agrupa nuevas, en preparación y listas. Tras iniciar la preparación se puede marcar cada producto o toda la comanda como lista. Se muestran tiempo transcurrido, alerta textual según umbral, tipo, estación y observaciones. El modo de pantalla completa amplía el tablero. Las comandas listas se muestran durante 24 horas y se conservan en el historial.

Cuando se modifica o retira una línea enviada, la comanda guarda una referencia a la original, la cantidad previa, la revisión y el motivo. Los cambios de una línea que ya comenzó a prepararse se protegen con permisos de ajuste y cancelación. Las comandas de traslado y cancelación son informativas. Su confirmación no cambia la preparación de una línea vigente.

El traslado actualiza el destino en mesa y emite avisos para cocina cuando hay productos despachados. Los documentos históricos conservan la mesa de la emisión.
