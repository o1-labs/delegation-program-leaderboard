# uptime-navigator-lite

A minimal read-only navigator over the `submissions` table written by
`uptime-service-backend`. Single container: Flask API + static HTML/JS,
served on port 8080.

> **Looking for what each metric means and where it's computed?**
> See [`METRICS.md`](METRICS.md) — full reference with line-pointers
> to the SQL/Python and the mapping to production's score formula.
> Limitations are tracked in
> [issue #9](https://github.com/o1-labs/delegation-program-leaderboard/issues/9).

## Endpoints

| Path | Purpose |
|---|---|
| `GET /` | Static page (`web/index.html`) |
| `GET /api/submitters` | Distinct submitters with submission counts, last/first seen, valid/invalid + chain-verified counters |
| `GET /api/submitter/<pubkey>` | Most recent 100 submissions for one BP |
| `GET /api/uptime/<pubkey>` | Bucketed activity over a window with coverage % |
| `GET /api/leaderboard` | Production-equivalent score + score_percent per BP |
| `GET /api/summary` | Daily counts per submitter |
| `GET /healthz` | DB-reachable ping |

## Environment

| Variable | Required | Notes |
|---|---|---|
| `POSTGRES_HOST` | yes | |
| `POSTGRES_PORT` | no | defaults to `5432` |
| `POSTGRES_DB` | yes | |
| `POSTGRES_USER` | yes | |
| `POSTGRES_PASSWORD` | yes | |
| `POSTGRES_SSLMODE` | no | defaults to `disable` |
| `WHITELIST` | no | comma-separated submitter pubkeys; when set, all queries filter to this set |

## Local smoke test

```bash
docker build -t uptime-navigator-lite:dev .
docker run --rm -p 8080:8080 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_DB=coordinator \
  -e POSTGRES_USER=o1labs \
  -e POSTGRES_PASSWORD=secret \
  uptime-navigator-lite:dev
curl localhost:8080/healthz
curl localhost:8080/api/submitters
```

## Published image

`ghcr.io/o1-labs/uptime-navigator-lite:<tag>` — pushed by
`.github/workflows/lite-image.yml` on tag push or `workflow_dispatch`.

## Chain cross-validator (CronJob)

The same image, invoked with `python3 /app/api/verifier.py` instead of
`gunicorn`. Cross-checks each new submission against `archive-node-api`
to populate the `verified` / `block_creator` / `validation_error`
columns. Wired up via the `verifier.*` values in
`o1-labs/helm-charts/uptime-navigator-lite/values.yaml`. Full
definition and trade-offs in
[`METRICS.md`](METRICS.md#the-verifier-how-verified-and-block_creator-get-populated).
