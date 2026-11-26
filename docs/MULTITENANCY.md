# Multitenancy

Cada usuario puede tener una membresía por restaurante. La sesión conserva el restaurante seleccionado. La API verifica que la membresía, el usuario y el restaurante estén activos. El slug de la URL se compara con el restaurante de esa sesión. Los usuarios de plataforma operan a través de rutas autorizadas por separado.

Un rol pertenece a un restaurante y las claves foráneas compuestas impiden asociar un rol de otro restaurante a una membresía. Las consultas de equipo filtran por el ID autorizado. Los cinco roles iniciales reciben permisos granulares. El permiso `users.manage` protege el acceso al equipo, y el servidor valida los permisos efectivos del rol que se intenta asignar.

La configuración del plan elimina los permisos FEL del contexto Básico. Los datos de restaurantes diferentes se verifican en pruebas de API y SQLite.
