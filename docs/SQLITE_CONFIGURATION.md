# SQLite

El archivo inicial es `backend/.data/raizfood.db`. SQLAlchemy resuelve las rutas relativas con respecto a `backend`, incluso cuando la migración se inicia desde la raíz. Cada conexión establece WAL, `synchronous=FULL`, `foreign_keys=ON` y un `busy_timeout` configurable que por defecto vale 10000 ms. El arranque verifica que Alembic haya alcanzado la revisión actual.

Mantén la base, el diario y los archivos auxiliares en disco local persistente. Los archivos de operaciones y pruebas quedan fuera del directorio público de Next.js. Alembic usa operaciones batch cuando corresponde.
