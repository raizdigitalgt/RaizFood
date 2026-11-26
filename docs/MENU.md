# Menú del restaurante

Categorías, platillos, variantes, grupos de modificadores y áreas de preparación se gestionan desde el panel del restaurante. Los nombres de categorías y grupos y los códigos de platillos y variantes se normalizan con NFKC, comparación sin distinción de mayúsculas y espacios internos consolidados. La unicidad se aplica por restaurante. El orden usa una posición numérica.

Los precios se almacenan como centavos enteros. La variante puede reemplazar el precio base o aplicarle un ajuste firmado. Cada grupo declara un mínimo y un máximo. Cada opción se puede elegir una vez por unidad. La cotización aplica precio base o variante, suma extras y multiplica el resultado por la cantidad. Un grupo inactivo deja de participar. Los precios registrados permanecen en el historial.

`GET /api/restaurants/{slug}/catalog` devuelve categorías y platillos activos, disponibilidad manual, variantes, modificadores y áreas de preparación. Las asociaciones se recuperan por lote. `POST /api/restaurants/{slug}/catalog/{itemId}/quote` valida disponibilidades, variante, selección de modificadores y cantidad antes de cotizar. Estos endpoints preparan el POS de la Fase 4. Los costos por receta se incorporan en la Fase 6.

Archivar conserva los registros y sus vínculos. Una categoría archivada deja fuera del catálogo sus platillos aunque conserven su estado individual. La duplicación copia vínculos de imágenes, grupos y variantes y exige un nuevo código.
