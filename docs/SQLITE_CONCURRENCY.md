# Concurrencia de SQLite

Las escrituras de altas y sesiones usan `BEGIN IMMEDIATE` antes de leer datos que influyen en la escritura. Así, dos solicitudes no pueden ocupar el último cupo al mismo tiempo. Argon2 se ejecuta antes de reservar la escritura en los flujos de alta. Después se vuelve a comprobar la autorización y el estado vigente.

Si SQLite devuelve BUSY o LOCKED, la API responde 503 con `Retry-After`. Las acciones de escritura no se repiten automáticamente ante ese resultado. Las restricciones únicas de slug, cuenta y membresía evitan duplicar altas. Las pruebas usan SQLite en archivo y verifican tanto la carrera por el último cupo como un bloqueo sostenido.
