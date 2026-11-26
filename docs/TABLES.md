# Áreas, salones y mesas

Las áreas de atención determinan cómo se agrupan las mesas. Las áreas de preparación se administran de forma independiente y pueden asignarse a platillos. Ambos catálogos permiten marcar áreas inactivas y cambiar su orden.

Crear un lote requiere un área, prefijo, cantidad, primer número y capacidad. El lote de hasta 100 mesas se inserta dentro de una transacción. Si un número ya existe en el área, se revierte todo el lote. El mismo número es válido en otra área.

La administración permite Disponible, En limpieza y Fuera de servicio. Ocupada, Reservada y Pendiente de cobro están reservados a la operación del POS. `GET /api/restaurants/{slug}/catalog/tables` consulta mesas de áreas activas y solo devuelve datos del restaurante seleccionado.
