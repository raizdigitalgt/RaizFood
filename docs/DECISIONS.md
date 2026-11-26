# Decisiones

- API y navegador comparten un origen para simplificar cookies y verificación de origen en operaciones mutables.
- Cada membresía tiene un rol en esta fase. La capacidad administrativa se contabiliza por el permiso efectivo de gestionar usuarios, roles o configuración.
- Se conserva el hash de cada refresh token hasta el vencimiento de su sesión para detectar reutilización. Las credenciales de acceso consultan el estado de la sesión.
- Las pantallas muestran operaciones respaldadas por endpoints y datos persistidos.
- El plan de catálogo puede cambiar. El contrato y cada período de renovación conservan la versión elegida.
- El estado operativo de la suscripción se obtiene de sus fechas y de las decisiones manuales. El mantenimiento materializa las alertas, mientras que la autorización consulta el estado efectivo.
- Se guardan imágenes decodificadas y normalizadas a PNG en SQLite para que respalden junto a los datos. Los formatos de entrada admitidos para logotipos son PNG, JPEG, WebP e ICO.
- Un correo comercial se reclama en una transacción antes del envío. Si el proceso se interrumpe después de reclamarlo, el trabajo queda en revisión para evitar reenvíos automáticos de resultado incierto.
