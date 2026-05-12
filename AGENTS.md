# AGENTS.md

Guidance for AI coding agents (Codex, Cursor, Aider, Jules, Claude Code, …) working in this repository. Humans should start with [`README.md`](./README.md); agents should start here.

Claude Code users: [`CLAUDE.md`](./CLAUDE.md) carries the same information in the format Claude expects. The two files are kept in sync — pick whichever your tooling reads automatically.

## What this repo is

A two-service containerised application that surfaces Mina Protocol's Delegation Program SNARK-work uptime data:

- **`web/`** — PHP 8 + Apache frontend, public leaderboard UI. Queries Postgres directly.
- **`api/`** — Flask REST API with Swagger UI. Independent of `web/`.

Both connect to the same external PostgreSQL database. There is **no** call from `web/` to `api/`.

## Code map

```
api/
  minanet_app/flask_api.py    ← all routes; start here for API changes
  minanet_app/config.py       ← env → BaseConfig
  minanet_app/db_health.py    ← connection retry + readiness logic
  minanet_app/api_spec*.yml   ← Swagger response schemas (edit these, not docstrings)
  diagnose_connection.py      ← standalone DB diagnostic
web/
  index.php                   ← page shell
  showDataForTabOne.php       ← leaderboard table renderer
  getPageDataForSnark.php     ← AJAX data fetch
  connectionsnark.php         ← PDO connection
  config.php                  ← env → PHP config (URLs)
Justfile                      ← canonical build/run commands
docker-compose.yaml           ← service definitions, env_file: .env
.env.example                  ← every supported env var, with defaults
.github/workflows/publish.yml ← builds + pushes both images to ghcr.io on tag
```

## How to run it

```bash
cp .env.example .env       # fill in DB credentials
just build-all
just launch-all            # web on :80, api on :5000
```

Per-service recipes: `build-web`, `build-api`, `launch-web`, `launch-api`, `destroy-web`, `destroy-api`, `destroy-all`. Run `just` (no args) to list them.

There is no language-level test suite in this repo. To verify a change end-to-end:

1. `just build-<component>` — confirms Docker build succeeds.
2. `just launch-<component>` — confirms the container starts.
3. For the API: `curl localhost:5000/health/ready` should return `200` with `status: ready`.
4. For the web: open `http://localhost:80` and confirm the leaderboard renders.

If you can't run Docker in your sandbox, say so explicitly in your report rather than claiming success.

## Conventions

- **Environment-driven config.** Both services read everything from env vars. Never hard-code hosts, ports, credentials, or URLs — add to [`.env.example`](./.env.example) and the relevant config file ([`api/minanet_app/config.py`](./api/minanet_app/config.py) or [`web/config.php`](./web/config.php)).
- **`just` is the canonical interface.** When you add a new buildable artefact or runnable service, add a recipe to [`Justfile`](./Justfile).
- **Pinned dependencies.** [`api/requirements.txt`](./api/requirements.txt) pins exact versions. Upgrade deliberately and as a single focused change.
- **Swagger schemas live in YAML.** Add or edit response shapes in [`api/minanet_app/api_spec*.yml`](./api/minanet_app/) and reference them with `@swag_from(...)` — don't inline schemas in `flask_api.py`.
- **Health endpoints are load-bearing.** `/health` and `/health/ready` are consumed by container orchestrators. Don't rename or change their response contract without coordinating a deployment update.

## Gotchas

- **`LOGGING_LOCATION` default crashes in containers.** The default `./application.log` may be unwritable. For containerised deployments set `LOGGING_LOCATION=""` to switch to console-only logging.
- **Web does *not* call the API.** Changing an API response shape does not affect the leaderboard UI — and vice versa. Make sure your change targets the right component.
- **`IGNORE_APPLICATION_STATUS=1` is a test-mode flag for `web/` only.** Setting it in production bypasses the `application_status = true` filter and exposes applicants who have not been accepted. The API has no equivalent flag.
- **Image publish on tag push.** [`/.github/workflows/publish.yml`](./.github/workflows/publish.yml) builds and pushes to `ghcr.io` whenever a tag is pushed. Tag deliberately.
- **The web image bakes PHP files at build time** — they're not bind-mounted. Rebuild after editing.

## What not to touch without asking

- `.github/workflows/publish.yml` — affects every consumer of the published images.
- `Dockerfile` base image pins (`python:3.12`, `php:apache`) — drift here cascades into runtime behaviour and dependency compatibility.
- Database query logic in [`web/showDataForTabOne.php`](./web/showDataForTabOne.php) and [`web/getPageDataForSnark.php`](./web/getPageDataForSnark.php) — small changes can silently exclude or duplicate participants.
- Swagger `basePath` / `host` in [`api/minanet_app/flask_api.py`](./api/minanet_app/flask_api.py) — downstream tooling depends on the published API surface.

## When in doubt

- Read [`README.md`](./README.md) for the human framing.
- Read [`api/README.md`](./api/README.md) and [`web/README.md`](./web/README.md) for component-level detail (env vars, endpoints, troubleshooting).
- Check [`.env.example`](./.env.example) — it is the most up-to-date catalogue of supported environment variables.
- For Claude-Code-specific guidance (sessions, planning, memory): [`CLAUDE.md`](./CLAUDE.md).
