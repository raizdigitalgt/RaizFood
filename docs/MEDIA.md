# Multimedia

La biblioteca permite crear carpetas y subcarpetas, subir varias imágenes, navegar, buscar, renombrar y mover registros. El backend comprueba que el movimiento no forme un ciclo y que la carpeta destino pertenezca al restaurante activo. Las relaciones impiden borrar carpetas con contenido e imágenes que sigan referenciadas, incluso si el registro que las usa está archivado.

Se aceptan JPG, JPEG, PNG, WebP y AVIF. `RESTAURANT_IMAGE_MAX_BYTES` establece el límite por archivo y tiene un valor inicial de 8388608 bytes. El suﬁjo del nombre sirve como etiqueta. El formato se determina al decodificar el contenido. Pillow normaliza orientación, conserva transparencia y genera una versión WebP de hasta 1800 px por lado y otra de hasta 320 px. Se descartan los metadatos del original. [Formatos compatibles de Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)

Los archivos se almacenan como BLOB en el SQLite persistente con una clave compuesta por restaurante y archivo. Así se incluyen en el respaldo consistente que ya genera la aplicación. Para servir una imagen, la API comprueba la sesión, los permisos y el alcance del archivo. El cliente no recibe una ruta física.
