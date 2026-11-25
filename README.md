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
| `LLM_API_KEY` | Clave del proveedor del LLM (Groq). Sin ella `POST /capturas` responde 503 y la app usa el formulario manual |
| `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT_S` | Modelo (por defecto `openai/gpt-oss-20b`), URL compatible con OpenAI y tiempo máximo por llamada |
| `LIMITES_ACTIVOS` | `true` por defecto; `false` apaga los límites de tasa (lo usan las pruebas) |
| `LIMITE_LOGIN_POR_MIN`, `LIMITE_CAPTURAS_POR_MIN`, `LIMITE_RESUMEN_POR_MIN` | Peticiones por minuto: 10, 20 y 10 por defecto; `0` desactiva ese límite |

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

## API (fase 3)

| Ruta | Función |
|---|---|
| `POST /capturas` | Recibe `{"texto": "..."}`, guarda el mensaje y devuelve la propuesta ya resuelta (201) con estado `pendiente` |
| `GET /capturas/{id}` | Propuesta vigente; las pendientes viven en la base, no en memoria |
| `POST /capturas/{id}/confirmar` | Inserta la fila real (actividad, registro de tiempo o meta). Idempotente: confirmar dos veces devuelve el mismo resultado |
| `POST /capturas/{id}/corregir` | Recibe `{"campos": {...}}` con los campos cambiados, los guarda como correcciones e inserta la fila corregida |
| `POST /capturas/{id}/descartar` | Cierra sin insertar. Idempotente |
| `GET /capturas/metricas` | Por tipo: aceptadas, corregidas, descartadas, `porcentaje_sin_correccion` y `promedio_campos_corregidos` |

La respuesta trae `campos` (la propuesta resuelta, con la forma del `POST` de la entidad),
`pendientes` (campos que el sistema no pudo resolver) y `resultado_id` (la fila creada tras
confirmar o corregir).

- **El modelo propone nombres; el código resuelve.** Materia y categoría se buscan entre las del
  usuario sin acentos ni mayúsculas. Si no hay coincidencia única, el campo queda vacío y aparece
  en `pendientes`. Las fechas relativas ("el viernes", "mañana a las 5 pm") se calculan en código
  con la zona horaria del usuario.
- **Reglas de fecha.** Una actividad sin hora vence a las 23:59. "La próxima semana" es el lunes
  siguiente. Una fecha pasada o una hora ambigua ("a las 5") no se adivinan: el campo queda en
  `pendientes`. Un registro de tiempo sin fecha termina ahora; con día pero sin hora no se inventa
  el inicio.
- **Qué exige confirmar.** Los campos obligatorios de la entidad (por ejemplo `categoria_id`).
  Si faltan, `422` con `codigo = "captura_incompleta"`. Los opcionales marcados en `pendientes`
  se confirman vacíos.
- **Respaldo.** Si el proveedor falla, agota el tiempo o devuelve JSON inválido tras un
  reintento, la respuesta es `503` con `codigo = "extraccion_no_disponible"` y no se guarda nada;
  la app abre el formulario manual.
- **Estados.** `pendiente`, `aceptada`, `corregida` y `descartada`. Confirmar una descartada o
  corregir y descartar una ya confirmada responde `409`.
- **Límite conocido.** La conexión del pool queda tomada mientras se espera al LLM (hasta dos
  intentos de `LLM_TIMEOUT_S`); con el pool de 5 conexiones, varias capturas simultáneas lentas
  pueden agotarlo.

Requiere las migraciones 000 a 007 de `kairo-bd`. Para medir el porcentaje aceptado sin
corrección con mensajes reales: `uv run python -m scripts.medir_extraccion mensajes.txt
--materias "Redes,Cálculo"` (un mensaje por línea; imprime la propuesta resuelta de cada uno).

## API (fase 4)

| Ruta | Función |
|---|---|
| `GET/POST /recordatorios` | Lista y crea avisos. Cada uno apunta a exactamente una actividad, un evento o una meta; `momento` debe traer zona horaria |
| `PATCH /recordatorios/{id}` | Reprograma (`momento`) o cancela (`estado_envio = "cancelado"`) solo mientras esté `pendiente`; después, 409 `recordatorio_cerrado` |
| `GET /autoevaluaciones` | Últimas semanas evaluadas |
| `GET/PUT /autoevaluaciones/{semana}` | `semana` es el lunes (`2026-11-16`). El `PUT` crea o actualiza `estado_animo`, `satisfaccion` (1 a 5) y `nota`; rechaza lunes inexistentes y semanas futuras |
| `POST /telegram/vinculo` | Con sesión: devuelve un código de 8 caracteres que vale 10 minutos y se canjea una vez |
| `POST /telegram/webhook` | Lo llama Telegram; exige la cabecera `X-Telegram-Bot-Api-Secret-Token` |
| `POST /interno/recordatorios/despachar` | Lo llama `pg_cron` cada 5 minutos con `Authorization: Bearer INTERNO_SECRET`; no aparece en el OpenAPI |

- **Vinculación.** El usuario genera el código en la app y envía `/vincular CODIGO` al bot. Solo se
  guarda el SHA-256 del código. `kairo_app` ya no puede escribir `telegram_id` directamente: lo
  fija la función `kairo_vincular_telegram`, y un Telegram que ya pertenece a otra cuenta no
  consume el código.
- **El bot es un adaptador.** Un Telegram sin vincular solo recibe instrucciones. Una vez
  vinculado: `/tarea <título>`, `/timer [categoría|stop]`, `/meta`, `/ayuda`. El texto libre pasa
  por el mismo pipeline de `/capturas` y el bot responde con botones Confirmar y Descartar que
  llaman a los mismos servicios. Si falla el proveedor de IA, el bot lo dice y no guarda nada.
- **Mensajes legibles.** El bot muestra fechas como `vie 27 nov, 23:59` en la zona del usuario y los
  nombres de categoría y materia, no identificadores. Si el mensaje no dice la modalidad de una
  actividad, pregunta con botones (Presencial, En línea, Mixta) y guarda al elegir; esa elección
  no cuenta como corrección en las métricas del pipeline. `/start CODIGO` vincula igual que
  `/vincular CODIGO`, para abrir el bot desde la app con `https://t.me/<bot>?start=CODIGO`.
- **Despacho.** Corre con `set local role kairo_worker`, que solo puede leer lo necesario para armar
  el texto y actualizar `estado_envio`, `intentos`, `enviado_en` y `ultimo_error`. Toma hasta 20
  pendientes vencidos con `for update skip locked`, de modo que dos ejecuciones simultáneas no
  envían lo mismo. Un fallo se reintenta en el siguiente ciclo y al tercero queda `fallido`; un
  usuario sin Telegram queda `fallido` de inmediato.
- **Límite conocido.** Si Telegram acepta el mensaje y la transacción falla al confirmar, el
  recordatorio se reenvía en el siguiente ciclo (entrega al menos una vez).
- **Webhook.** Se registra una vez con `setWebhook` indicando `url` y `secret_token`
  (el mismo valor de `TELEGRAM_WEBHOOK_SECRET`). El servicio siempre responde 200 a un
  update con secreto válido, aunque falle internamente, para que Telegram no reintente en bucle.

Requiere las migraciones 000 a 010 de `kairo-bd`. Variables nuevas: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_WEBHOOK_SECRET` e `INTERNO_SECRET` (mínimo 32 caracteres aleatorios). Con
cualquiera de los dos secretos vacío, su endpoint rechaza todo.

## API (fase 5)

| Ruta | Función |
|---|---|
| `GET /reportes/agenda` | Actividades abiertas con vencimiento futuro y eventos que no han terminado, en orden. Parámetros `dias` (1 a 90, 7 por defecto) y `limite` (1 a 200, 50) |
| `GET /reportes/carga-semanal` | Por semana y materia: actividades con vencimiento, pendientes y minutos registrados. `semanas_atras` (3) y `semanas_adelante` (4) |
| `GET /reportes/metas` | Progreso de las metas activas en su periodo actual, con `porcentaje` y `cumplida` |
| `GET /reportes/pipeline` | Desempeño de la captura por IA: total, aceptadas, corregidas, descartadas y porcentaje aceptado sin corrección, por tipo de entidad |
| `GET /reportes/carga-vs-descanso` | Por semana: minutos académicos, de sueño y de ejercicio junto con ánimo y satisfacción. `semanas` (1 a 52, 8) |
| `GET /reportes/resumen` | Reúne las cifras anteriores y pide al LLM un texto breve |

- **Las cifras vienen de SQL.** Los reportes leen vistas de `kairo-bd` que filtran por el usuario de la sesión.
  El LLM solo redacta: recibe las cifras sin identificadores y con títulos recortados a 80 caracteres.
- **El texto se verifica.** Si contiene un número que no está en las cifras, se descarta: `texto` sale
  `null` y `motivo_sin_texto` vale `texto_no_verificado`. Si el proveedor falla o no está configurado,
  la respuesta trae las cifras igualmente (`motivo_sin_texto` con la causa o `sin_configurar`).

### Seguridad

- Todas las consultas corren con el rol `kairo_app`, sin `DELETE` (salvo `actividad_etiqueta`) ni DDL, y con RLS.
- Los logs no incluyen texto de mensajes ni el token del bot (los clientes `httpx` se registran solo desde `WARNING`).
- Los errores usan siempre `{"codigo", "detalle"}`.

### Límites de tasa

Ventana deslizante de 60 s en memoria, por proceso. `POST /auth/login` se limita por correo y por origen
(el triple del límite), `POST /capturas` (y el bot) por usuario y `GET /reportes/resumen` por usuario.
Al excederse responde 429 `demasiadas_peticiones` con `Retry-After`. Con varias instancias cada una
cuenta por separado. Detrás de Render se confía en `X-Forwarded-For` (`--proxy-headers`).

El contrato completo está en `docs/openapi.json`; se regenera con
`uv run python -m scripts.exportar_openapi` y una prueba falla si está desactualizado.

Requiere las migraciones 000 a 011 de `kairo-bd`.

## Estructura

```
app/
  main.py        creación de la app, CORS, lifespan del pool y registro de peticiones
  api/           salud y router `/api/v1`
  modules/       un paquete por recurso: router, repository, schemas (y service)
  services/      extracción con LLM, resolución de referencias y fechas, cliente de Telegram
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
`sslmode=require`), `JWT_SECRET`, `CORS_ORIGINS`, `LLM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` e `INTERNO_SECRET`. El plan gratuito se apaga a los 15
minutos sin tráfico y la primera petición tarda cerca de un minuto.
