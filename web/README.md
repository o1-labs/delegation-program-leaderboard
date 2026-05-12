# Delegation Program Leaderboard — Web Frontend

PHP frontend that renders the Mina Delegation Program uptime leaderboard. It queries the Delegation Program PostgreSQL database **directly** — it does not call the sibling API in [`/api`](../api/README.md).

## Stack

- PHP 8 on `php:apache` (Debian)
- Bootstrap 4, vanilla JS, jQuery (assets in [`assets/`](./assets/))
- `pdo_pgsql` for database access
- Apache with `ssl` + `rewrite` modules enabled (see [`000-default.conf`](./000-default.conf))

## File map

| File | Role |
|------|------|
| [`index.php`](./index.php) | Page shell, tabs, top-level layout. |
| [`showDataForTabOne.php`](./showDataForTabOne.php) | Renders the leaderboard table. |
| [`getPageDataForSnark.php`](./getPageDataForSnark.php) | Paginated data fetch for AJAX calls. |
| [`connectionsnark.php`](./connectionsnark.php) | PDO connection to the Delegation Program DB. |
| [`config.php`](./config.php) | Reads configurable URLs from environment with defaults. |
| [`Dockerfile`](./Dockerfile) | Build recipe (php:apache + pdo_pgsql). |
| [`000-default.conf`](./000-default.conf) | Apache vhost config. |
| [`php.ini`](./php.ini) | PHP runtime config (copied into `$PHP_INI_DIR/conf.d/`). |

## Configuration

All configuration is via environment variables. Copy the root [`.env.example`](../.env.example) to `.env` and edit the values:

```bash
cp ../.env.example ../.env
```

### Required — database connection

| Variable | Purpose |
|----------|---------|
| `DB_SNARK_HOST` | PostgreSQL host. |
| `DB_SNARK_PORT` | PostgreSQL port (typically `5432`). |
| `DB_SNARK_USER` | DB user (read-only role recommended). |
| `DB_SNARK_PWD` | DB password. |
| `DB_SNARK_DB` | Database name. |

### Optional — test mode

| Variable | Effect |
|----------|--------|
| `IGNORE_APPLICATION_STATUS=1` | Skip the `application_status = true` filter when building the leaderboard. Use **only** in test environments — production leaderboards must keep this unset. |

### Optional — configurable URLs

All have sensible defaults pointing at `minaprotocol.com` / `docs.minaprotocol.com` (see [`config.php`](./config.php)):

- `DELEGATION_PRODUCERS_URL`
- `DELEGATION_FORM_URL`
- `DELEGATION_POLICY_URL`
- `DELEGATION_GUIDELINES_URL`
- `API_DOCS_URL`
- `FOUNDATION_PROGRAM_URL`
- `FOUNDATION_GUIDELINES_URL`

## Build & run

From the repo root, using `just` (preferred):

```bash
just build-web     # docker build -t leaderboard-web ./web
just launch-web    # docker-compose up -d leaderboard-web   (binds :80)
just destroy-web   # docker-compose down leaderboard-web
```

Without `just`:

```bash
docker build -t leaderboard-web ./web
docker run --env-file ../.env --name leaderboard-web -p 80:80 -d leaderboard-web
```

Then open <http://localhost:80>.

## Common issues

- **Empty leaderboard.** The query filters by `application_status = true AND score IS NOT NULL`. Set `IGNORE_APPLICATION_STATUS=1` to confirm whether the filter is the cause, then verify the underlying rows in the `nodes` table.
- **`Connection refused` / `could not translate host name`.** Confirm `DB_SNARK_HOST` is reachable from inside the container (try `docker exec -it web getent hosts $DB_SNARK_HOST`).
- **TLS / mixed-content errors behind a proxy.** Apache has `ssl` and `rewrite` enabled in the image, but TLS termination is expected to happen at the ingress / load balancer in production.

## Rebuilding after changes

The PHP files are baked into the image at build time, not bind-mounted. After editing any file under `web/`, rebuild:

```bash
just build-web && just launch-web
```
