"""Environment -> Settings. Every knob is an env var; see graphql/README.md."""

import os
from dataclasses import dataclass

from psycopg.conninfo import make_conninfo

REQUIRED = ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


def _int(env, name, default, lo, hi):
    raw = env.get(name)
    value = default if raw in (None, "") else int(raw)
    if not lo <= value <= hi:
        raise ValueError(f"{name}={value} is outside [{lo}, {hi}]")
    return value


@dataclass(frozen=True)
class Settings:
    conninfo: str
    # A BP is "up" if its last submission is at most this old. The default
    # is two survey intervals (2 x 20 min).
    is_up_minutes: int = 40
    max_page_size: int = 500
    max_query_depth: int = 8
    statement_timeout_ms: int = 10_000
    pool_max_size: int = 4
    # activity(): longest range and most buckets per BP in one query.
    max_activity_days: int = 92
    max_activity_buckets: int = 2500
    # Buckets of all activity() fields in one request, e.g. a page of BPs.
    max_request_buckets: int = 50_000

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        conninfo = make_conninfo(
            host=env["POSTGRES_HOST"],
            port=env.get("POSTGRES_PORT") or "5432",
            dbname=env["POSTGRES_DB"],
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
            sslmode=env.get("POSTGRES_SSLMODE") or "prefer",
            application_name="uptime-graphql",
        )
        return cls(
            conninfo=conninfo,
            is_up_minutes=_int(env, "IS_UP_WINDOW_MINUTES", 40, 1, 1440),
            max_page_size=_int(env, "MAX_PAGE_SIZE", 500, 1, 5000),
            max_query_depth=_int(env, "MAX_QUERY_DEPTH", 8, 3, 20),
            statement_timeout_ms=_int(env, "STATEMENT_TIMEOUT_MS", 10_000, 100, 600_000),
            pool_max_size=_int(env, "DB_POOL_MAX_SIZE", 4, 1, 50),
            max_activity_days=_int(env, "MAX_ACTIVITY_DAYS", 92, 1, 3660),
            max_activity_buckets=_int(env, "MAX_ACTIVITY_BUCKETS", 2500, 1, 100_000),
            max_request_buckets=_int(env, "MAX_REQUEST_BUCKETS", 50_000, 1, 10_000_000),
        )
