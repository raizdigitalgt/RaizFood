# Respaldos y restauración

## Crear y verificar

El módulo Respaldos crea copias mediante la API `sqlite3.Connection.backup`, que incluye el contenido confirmado en WAL. Una copia independiente incluye los logotipos y comprobantes porque se almacenan en SQLite. Se comprueba `integrity_check` y `foreign_key_check`, se calcula SHA-256 y se conserva un manifiesto JSON con nombre, revisión de Alembic, tamaño, fecha y resultado. Conserva juntos el archivo SQLite y su manifiesto. [Documentación de sqlite3](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup)

Configura `BACKUP_DIRECTORY` en un directorio privado fuera de rutas públicas. El valor predeterminado es el subdirectorio `backups` de la carpeta de la base. En Linux se crean archivos con permisos 0600 y el directorio con 0700. En Windows aplica ACL al directorio de trabajo para la cuenta de servicio y operadores autorizados. Los respaldos incluyen usuarios y datos comerciales, además de credenciales cifradas. Conserva `ENCRYPTION_KEY` en el gestor de secretos por separado.

El permiso `backups` cubre generar y verificar. La descarga requiere `backups.download`, reservado al superadministrador. Las operaciones quedan auditadas. La retención programada conserva el respaldo verificado más reciente y expira copias gestionadas por el panel.

## Programar

Programa `scripts/maintenance.ps1` cada 15 minutos mediante el Programador de tareas de Windows con una cuenta con permisos sobre SQLite y el directorio de respaldo. Usa `powershell.exe -NoProfile -File RUTA_ABSOLUTA` como acción y configura evitar una segunda instancia simultánea. En Linux, ejecuta `bash /ruta/RaizFood/scripts/maintenance.sh` con systemd o cron como la cuenta propietaria del servicio. El intervalo y la retención de las copias se definen en el panel. El mantenimiento también revisa vigencias y procesa la cola de correo.

## Restaurar una copia independiente

Ejecuta desde `backend`, indicando un destino nuevo y confirmando la acción:

```powershell
.\.venv\Scripts\python.exe -m app.maintenance restore --source RUTA_AL_RESPALDO.db --target .data/restore/independent.db --confirm RESTAURAR
```

La CLI verifica la copia y el manifiesto antes de escribir. Para restaurar la base activa, detén la API y cualquier tarea programada, establece `MAINTENANCE_MODE=true`, usa la ruta de la base activa como destino y conserva el respaldo previo que crea la CLI. Después verifica revisión e integridad y reactiva los servicios. El procedimiento probado automatizadamente usa un destino independiente. Para regresar a Fase 1, usa el respaldo de revisión `0002` con los binarios de esa fase. El downgrade desde una base con roles nuevos o auditoría anónima está limitado para preservar la seguridad y el historial.
