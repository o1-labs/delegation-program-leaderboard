# Delegation Program Leaderboard — API

Flask REST API exposing the Mina Delegation Program SNARK-work uptime database. Ships with Swagger UI, response caching, Kubernetes-style health probes, and connection-retry logic.

## Stack

- Python 3.12 on `python:3.12`
- Flask 2.2, Flask-Caching, Flasgger (Swagger 2.0)
- `psycopg2` against PostgreSQL
- Health/diagnostics modules for container orchestration

## File map

| File | Role |
|------|------|
| [`minanet_app/flask_api.py`](./minanet_app/flask_api.py) | App entry point — all routes, Swagger config, error handlers. |
| [`minanet_app/config.py`](./minanet_app/config.py) | `BaseConfig` — pulls everything from env. |
| [`minanet_app/db_health.py`](./minanet_app/db_health.py) | Connection retry + health-check logic. |
| [`minanet_app/logger_util.py`](./minanet_app/logger_util.py) | Logger setup (file or console). |
| [`minanet_app/entrypoint`](./minanet_app/entrypoint) | Container entrypoint (`python flask_api.py`). |
| [`minanet_app/api_spec*.yml`](./minanet_app/) | Swagger response schemas referenced from route docstrings. |
| [`diagnose_connection.py`](./diagnose_connection.py) | Standalone DB connectivity diagnostic (DNS → TCP → auth → query). |
| [`Dockerfile`](./Dockerfile) | Build recipe. |
| [`requirements.txt`](./requirements.txt) | Pinned Python dependencies. |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness probe. Always 200 if Flask is up. |
| GET | `/health/ready` | Readiness probe. 200 only if DB is reachable. |
| GET | `/health/debug` | Verbose diagnostics. Available **only** when `DEBUG=true`. |
| GET | `/uptimescore/` | Latest uptime scores for all producers. |
| GET | `/uptimescore/<pubkey>` | Latest score for a single producer. |
| GET | `/uptimescore/<pubkey>/<dataType>/` | Historic series for a producer. |
| GET | `/uptimescore/<pubkey>/<dataType>/<scoreAt>/` | Score at a specific timestamp. |
| GET | `/apidocs/` | Swagger UI. |

Routes are defined in [`minanet_app/flask_api.py`](./minanet_app/flask_api.py) (see lines 70, 82, 115, 252–255).

## Configuration

Copy the root [`.env.example`](../.env.example) to `.env` and edit the values:

```bash
cp ../.env.example ../.env
```

### Required — database

| Variable | Purpose |
|----------|---------|
| `SNARK_HOST` | PostgreSQL host. |
| `SNARK_PORT` | PostgreSQL port (typically `5432`). |
| `SNARK_USER` | DB user. |
| `SNARK_PASSWORD` | DB password. |
| `SNARK_DB` | Database name. |

### Required — server

| Variable | Purpose |
|----------|---------|
| `API_HOST` | Bind address (typically `0.0.0.0` in containers). |
| `API_PORT` | Bind port (typically `5000`). |
| `SWAGGER_HOST` | Hostname embedded in the Swagger spec (e.g. `localhost:5000` or `uptime.minaprotocol.com`). |
| `CACHE_TIMEOUT` | Flask-Caching default TTL in seconds. |

### Optional — debug & resilience

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEBUG` | `false` | Enables Flask debug mode, pretty-printed JSON, and `/health/debug`. |
| `LOGGING_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `LOGGING_LOCATION` | `./application.log` | Log file path. **Set to empty string for console-only logging in containers.** |
| `DB_CONNECTION_TIMEOUT` | `10` | psycopg2 connect timeout in seconds. |
| `DB_RETRY_ATTEMPTS` | `3` | Number of connection retries before giving up. |

## Build & run

From the repo root, using `just` (preferred):

```bash
just build-api     # docker build -t leaderboard-api ./api
just launch-api    # docker-compose up -d leaderboard-api   (binds :5000)
just destroy-api   # docker-compose down leaderboard-api
```

Then open:
- Swagger UI: <http://localhost:5000/apidocs/>
- Readiness: <http://localhost:5000/health/ready>

Without `just`:

```bash
docker build -t leaderboard-api ./api
docker run --env-file ../.env --name leaderboard-api -p 5000:5000 -d leaderboard-api
```

## Troubleshooting

### Crash on startup with logging errors

The default `LOGGING_LOCATION=./application.log` tries to write to a path that may not exist or be writable inside the container. For containerised deployments, set:

```bash
LOGGING_LOCATION=""
```

This switches the logger to console-only — preferred in Kubernetes / Docker where logs should go to stdout/stderr.

### Database connection failures

1. Hit `/health/ready` — the response payload includes the DB error class and message.
2. If you need lower-level detail, run the diagnostic script from inside the container or from a host with the same network access:

   ```bash
   cd api && python diagnose_connection.py
   ```

   It tests DNS resolution, TCP reachability, authentication, and a minimal `SELECT`.

3. With `DEBUG=true`, `/health/debug` exposes the resolved connection parameters (no password) and recent retry attempts.

### Stale data after a config change

Responses are cached for `CACHE_TIMEOUT` seconds. Either wait it out or restart the container.

## Development notes

- The container `ENTRYPOINT` is [`minanet_app/entrypoint`](./minanet_app/entrypoint), which starts `cron` and `atd`, then execs `flask_api.py`. Cron is currently unused but kept for parity with historic deployments — feel free to slim it down if you're confident no scheduled job depends on it.
- Swagger response schemas live in separate YAML files (`api_spec*.yml`) and are referenced via `@swag_from(...)` decorators. Edit those rather than inlining schemas in the Python file.
- Dependencies are pinned in [`requirements.txt`](./requirements.txt). Upgrade deliberately — `Flask 2.x` and `Werkzeug 3.x` have a known ABI mismatch with some plugin versions.
