# kairo-backend

API de Kairo: gestor de actividades y tiempo con captura asistida por IA. FastAPI con
psycopg 3 (SQL a mano, sin ORM) sobre PostgreSQL en Supabase. El esquema vive en el
repo `kairo-bd`.

## Requisitos

- Python 3.13 y [uv](https://docs.astral.sh/uv/)
- Docker, para el Postgres local

## Puesta en marcha

```bash
cp .env.example .env
docker compose up -d db
uv sync
uv run uvicorn app.main:app --reload
```

La documentación interactiva queda en `http://localhost:8000/docs`.

## Variables de entorno

| Variable | Uso |
|---|---|
| `APP_ENV` | `development`, `test` o `production`. En producción `JWT_SECRET` es obligatorio |
| `DATABASE_URL` | Cadena de conexión a PostgreSQL, con TLS en Supabase |
| `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE` | Tamaño del pool de conexiones |
| `JWT_SECRET` | Al menos 32 caracteres en producción |
| `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Parámetros del token de acceso |
| `CORS_ORIGINS` | Orígenes permitidos, separados por coma |
| `LOG_LEVEL` | Nivel de logging; la salida es JSON, una línea por evento |

## Estructura

```
app/
  main.py        creación de la app, CORS, lifespan del pool y registro de peticiones
  api/           routers
  core/
    config.py    configuración tipada
    db.py        pool, transacción por petición y usuario para la RLS
    errors.py    formato de error único
    logging.py   logging estructurado
tests/
```

## Convenciones

- **Una transacción por petición.** La dependencia `Tx` entrega una conexión dentro de
  una transacción que se confirma al terminar y se revierte si hay un error.
- **Aislamiento por usuario.** `fijar_usuario` ejecuta `set_config('app.usuario_id', ..., true)`,
  equivalente parametrizable de `SET LOCAL`. Debe llamarse dentro de la transacción: con
  el pooler de Supabase en modo transacción, fijarlo a nivel de sesión mezclaría usuarios.
- **Errores.** Toda respuesta de error tiene la forma `{"codigo": "...", "detalle": "..."}`.
  Violaciones de único responden 409; de CHECK y de llave foránea, 422.
- **Health.** `GET /health` no toca la base; `GET /health/db` sí y responde 503 si no hay
  conexión.

## Pruebas y calidad

```bash
docker compose up -d db
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest
```

Las pruebas de base usan `DATABASE_URL` (por defecto, el Postgres del compose). El CI
corre lo mismo contra Postgres 17 y aplica antes las migraciones de `kairo-bd`.

## Despliegue en Render

`render.yaml` define un servicio web con Docker y `healthCheckPath: /health`. Variables
que se capturan a mano en Render: `DATABASE_URL` (cadena del pooler de Supabase con
`sslmode=require`), `JWT_SECRET` y `CORS_ORIGINS`. El plan gratuito se apaga a los 15
minutos sin tráfico y la primera petición tarda cerca de un minuto.
