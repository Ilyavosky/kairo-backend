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
| `DB_ROLE` | Rol al que cambia cada conexión (`set role`); las pruebas usan `kairo_app` para que la RLS aplique |
| `JWT_SECRET` | Al menos 32 caracteres en producción; en desarrollo hay uno por defecto |
| `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Parámetros del token de acceso |
| `CORS_ORIGINS` | Orígenes permitidos, separados por coma |
| `LOG_LEVEL` | Nivel de logging; la salida es JSON, una línea por evento |

## API (fase 1)

Todo bajo `/api/v1`. Autenticación con `Authorization: Bearer <token>`; el token sale de
`POST /auth/login`.

| Ruta | Función |
|---|---|
| `POST /auth/registro`, `POST /auth/login`, `GET /auth/yo` | Cuenta y sesión |
| `GET /categorias` | Catálogo del sistema y propias; filtro `ambito` |
| `GET/POST /materias`, `GET/PATCH /materias/{id}` | Materias; baja lógica con `activa: false` |
| `GET/POST /actividades`, `GET/PATCH /actividades/{id}` | Filtros `estado`, `materia_id`, `desde`, `hasta`, `limite`, `desplazamiento` |
| `POST /actividades/{id}/completar` | Pasa a `completada`; el trigger fija `completada_en` |
| `GET /calendario` | Fechas institucionales; filtros `periodo` y `tipo` |

Las fechas con hora (`vence_en`) deben llevar zona horaria. Las filas de otro usuario
responden 404, no 403. Esquema completo en `/docs`.

## API (fase 2)

| Ruta | Función |
|---|---|
| `GET/POST /eventos`, `GET/PATCH /eventos/{id}` | Eventos con `fin > inicio`; filtros `desde` y `hasta` (por traslape) y `materia_id` |
| `GET/POST /etiquetas` | Etiquetas únicas por usuario sin distinguir mayúsculas |
| `GET /actividades/{id}/etiquetas`, `PUT/DELETE /actividades/{id}/etiquetas/{etiqueta_id}` | Etiquetas de una actividad; `PUT` es idempotente |
| `POST /temporizador/iniciar`, `POST /temporizador/detener`, `GET /temporizador/actual` | Una sesión en curso por usuario (409 si ya hay una); al detener se crea el registro de tiempo; sin pausa |
| `GET/POST /registros-tiempo`, `GET/PATCH /registros-tiempo/{id}` | Filtros `desde`, `hasta`, `categoria_id` y `actividad_id`; el alta manual fija `origen = 'manual'` |
| `GET/POST /metas`, `GET/PATCH /metas/{id}` | Tipo `tiempo_acumulado` (minutos) o `numero_eventos` (registros de tiempo), periodo `dia`, `semana` o `mes`; solo mínimos |
| `GET /metas/{id}/progreso`, `GET /metas/historial` | Progreso del periodo actual calculado en SQL y evaluaciones de periodos cerrados |

Los periodos de las metas se calculan en la zona horaria del usuario y la semana empieza
el lunes. Requiere las migraciones 000 a 005 de `kairo-bd`.

## Estructura

```
app/
  main.py        creación de la app, CORS, lifespan del pool y registro de peticiones
  api/           salud y router `/api/v1`
  modules/       un paquete por recurso: router, repository, schemas (y service)
  core/
    config.py    configuración tipada
    db.py        pool, transacción por petición y usuario para la RLS
    auth.py      usuario de la petición y transacción con RLS
    errors.py    formato de error único
    security.py  hash de contraseñas y JWT
    sql.py       UPDATE parcial con identificadores seguros
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

Las pruebas de base usan `DATABASE_URL` (por defecto, el Postgres del compose) y necesitan
las migraciones de `kairo-bd` aplicadas. El CI corre lo mismo contra Postgres 17 y las
aplica antes. Las pruebas de la API corren con `DB_ROLE=kairo_app`: como superusuario la
RLS no se aplica y no probarían nada.

## Despliegue en Render

`render.yaml` define un servicio web con Docker y `healthCheckPath: /health`. Variables
que se capturan a mano en Render: `DATABASE_URL` (cadena del pooler de Supabase con
`sslmode=require`), `JWT_SECRET` y `CORS_ORIGINS`. El plan gratuito se apaga a los 15
minutos sin tráfico y la primera petición tarda cerca de un minuto.
