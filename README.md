# Delegation Program Leaderboard

Containerized leaderboard for Mina Protocol's Delegation Program. It surfaces SNARK-work uptime data from the Delegation Program PostgreSQL database, both as a public web page and as a documented REST API.

## Components

| Path | Stack | Port | Purpose |
|------|-------|------|---------|
| [`/web`](./web/README.md) | PHP 8 + Apache + Bootstrap 4 | `80` | Public leaderboard UI (queries Postgres directly). |
| [`/api`](./api/README.md) | Python 3.12 + Flask + Flasgger | `5000` | REST API + Swagger UI for uptime scores. |

Both containers connect **independently** to the same PostgreSQL database — the web frontend does *not* call the API.

## Quick start

```bash
cp .env.example .env        # fill in DB credentials
just build-all              # build both images
just launch-all             # start web on :80 and api on :5000
```

- Web UI: <http://localhost:80>
- Swagger UI: <http://localhost:5000/apidocs/>
- API readiness probe: <http://localhost:5000/health/ready>

Run `just` with no arguments to list every recipe.

## Repository layout

```
.
├── README.md              ← you are here
├── AGENTS.md              ← entry point for AI agents (Codex, Cursor, Aider, …)
├── CLAUDE.md              ← Claude Code-specific guidance
├── Justfile               ← canonical build/run commands
├── docker-compose.yaml    ← service definitions
├── .env.example           ← all supported environment variables
├── api/                   ← Flask API (see api/README.md)
├── web/                   ← PHP frontend (see web/README.md)
└── .github/workflows/     ← image publishing to ghcr.io on tag push
```

## For AI agents

Read [`AGENTS.md`](./AGENTS.md) first — it lists entry points, run/test commands, and the things you should *not* change without asking. Claude Code users also have [`CLAUDE.md`](./CLAUDE.md) with the same information formatted for Claude.

## Deployment

Tagged commits trigger `.github/workflows/publish.yml`, which builds and pushes both images to GitHub Container Registry (`ghcr.io`). Manual runs accept a `docker_tag_prefix` input for ad-hoc tags.
