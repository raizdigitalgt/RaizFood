# Punto de venta

En el panel de restaurante, abre **Punto de venta** o elige una mesa desde **Mesas**. El POS te permite abrir un borrador existente o crear uno en una modalidad habilitada en **Configuración → Operación**. Puedes asignar un cliente y, con permiso, otro mesero.

- Para consumo en mesa se seleccionan salón, mesa y comensales.
- Para llevar se pueden registrar cliente, teléfono, hora estimada y observaciones.
- Para entrega se solicitan nombre, teléfono y dirección. Se guardan referencia, costo de envío y estado interno de entrega.

El catálogo incluye búsqueda por nombre, descripción y código, categorías, destacados y las vistas compacta y con fotos. En un producto con variantes o extras, selecciona la presentación, indica cantidad y observaciones y revisa el importe. La API del catálogo valida las opciones y calcula el precio real al guardar.

El pedido se guarda en SQLite desde su creación y después de cada cambio. El selector de pedidos abiertos y el enlace del pedido permiten retomarlo tras cerrar el módulo o recargar la página. En móviles, el botón del pedido abre el carrito.

Confirma el pedido, envía a cocina, revisa los estados y solicita la cuenta cuando se hayan enviado todos los productos. Las acciones de transferencia, descuento, cancelación, división de cuentas y ajuste en preparación requieren permisos. La vista previa se puede abrir para el pedido completo o para una cuenta individual.

En **Configuración del POS** se ajustan el aviso de demora, los límites de descuento y las estaciones permitidas a los cocineros. Los indicadores del dashboard resumen pedidos, mesas y preparación con datos operativos. Los ingresos corresponden al módulo de cobro de la Fase 7.
