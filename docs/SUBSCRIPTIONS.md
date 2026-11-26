# Planes iniciales

| Plan | Precio mensual inicial | Administradores | Operativos | Total | FEL |
| --- | ---: | ---: | ---: | ---: | --- |
| Básico | Q150.00 | 1 | 4 | 5 | Deshabilitada |
| Pro | Q275.00 | 2 | 8 | 10 | Habilitada por plan |

Los precios en centavos se configuran antes de sembrar cada plan. Los roles con `users.manage`, `roles.manage` o `settings.manage` ocupan cupo administrativo. La transacción de alta cuenta solo usuarios y membresías activos. Las cuentas de plataforma quedan fuera del cupo. Editar un plan crea una versión nueva sin cambiar las condiciones de las suscripciones existentes. Archivar bloquea nuevas asignaciones. La selección explícita de otro plan aplica las condiciones nuevas tras verificar los cupos. El sistema conserva el historial de contratos y cambios. La gracia se puede actualizar desde la suscripción. Las fechas iniciales, el período de prueba y el descuento inicial se pueden corregir antes de registrar pagos o preparar renovaciones.

El último día disponible para operar es el anterior al vencimiento. Las pruebas y la gracia pueden habilitar operación durante sus fechas. Un contrato vencido, pendiente, suspendido o cancelado conserva consulta de resumen y permisos para historial cuando estén disponibles. Los restaurantes conservan el acceso inicial y los cupos de la versión seleccionada al registrarse hasta que se les asigne un contrato.

Cada período de cobro tiene un saldo en centavos. Los pagos pendientes y rechazados quedan fuera del saldo confirmado. El primer período pendiente se activa al cubrir el importe. En una renovación, la fecha final avanza cuando se confirma el importe íntegro del período contiguo. La reversión puede deshacer la última renovación aplicada cuando el contrato carece de períodos posteriores. Las opciones de pago se configuran desde el panel.
