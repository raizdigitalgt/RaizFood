# Pedidos y cuentas

La creación asigna un UUID, un correlativo por restaurante y la versión 1. Los estados operativos son borrador, confirmado, enviado, en preparación, listo, entregado y cancelado. Enviar publica las líneas nuevas. Cocina cambia la preparación y el mesero registra la entrega cuando todas las líneas estén listas. En pedidos a domicilio se puede registrar el despacho y la entrega al destinatario.

La cuenta tiene su propio estado. Pendiente de cobro permite editar productos y pedir la cuenta. La solicitud congela productos y descuentos hasta reabrir. El estado de mesa cambia a cuenta solicitada y sigue vinculado hasta que el pedido termine o se cancele. Pago parcial, pagado y revertido se reservan para la Fase 7.

Cada línea guarda nombre, código, variante, extras, ajuste, precio base, estación y precio unitario en centavos junto con sus referencias. El historial conserva las revisiones y motivos. Cambiar el menú afecta las próximas selecciones. Una edición de cantidad u observaciones que conserva las opciones retiene el precio unitario histórico.

Un descuento puede aplicarse a una línea o al pedido con importe fijo o porcentaje. El porcentaje viaja en puntos básicos. Se exige permiso, motivo y cumplimiento de los límites de configuración. Se aplican primero los descuentos por línea y después el general, con distribución por mayores restos. El mismo método conserva los centavos de envío y descuentos en todas las cuentas.

Dividir mueve cantidades hacia una cuenta nueva del mismo pedido. Combinar devuelve las cantidades a la cuenta principal. Los cambios de productos con varias cuentas requieren reunirlas antes. Las comandas siguen vinculadas a las líneas del pedido original. La cuenta preliminar permite consultar totales generales e individuales.

El historial puede filtrarse por fecha, estado, modalidad, mesa, usuario y búsqueda. Cada cambio registrado incluye actor, fecha y, según la operación, valores anteriores, nuevos y motivo.
