"""One-shot best-effort verifier — cross-checks submissions against the
best chain by temporal proximity.

The uptime-service-backend does not extract state_hash / height / slot from
the submitted binary payload, so we cannot match a submission to a specific
block by hash. Instead, for each submission at time T we look up the
best-chain blocks in archive-node-api whose `dateTime` falls within a small
window around T and classify the submission as:

We query with `inBestChain: true` rather than `canonical: true` because
canonical (= finalized k blocks deep) lags far behind the tip on a young
testnet — at the time of writing, only the genesis block was canonical
while the chain was at height ~235.

- `verified=true`, `block_creator=submitter` — when a block in the window
  was produced by the submitter (strong signal: self-produced).
- `verified=true`, `block_creator=<creator>`, `validation_error="submission-near-block-not-by-self"`
  — when blocks exist in the window but none were produced by the submitter
  (weak signal: chain healthy, BP was observing).
- `verified=false`, `validation_error="no-block-near-submission-time"`
  — when no best-chain block exists in the window (likely chain unhealthy at
  that time, or the submission referred to a dropped fork).

This is intentionally lossy: it cannot distinguish a real submission from a
replay or a signed-but-fake submission. It only measures "did this BP submit
near times when the chain was producing canonical blocks". For stricter
verification, the upstream uptime-service-backend would need to extract the
submission's state_hash and we'd switch to height-anchored lookups.

Designed to be invoked from a Kubernetes CronJob — runs once and exits. Safe
to run concurrently or on overlapping windows; the WHERE clause makes the
work idempotent.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import requests

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("verifier")


def env(name: str, default: Optional[str] = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        log.error("Required env var %s is not set", name)
        sys.exit(2)
    return val


ARCHIVE_URL = env("ARCHIVE_NODE_API_URL")
BATCH_SIZE = int(os.environ.get("VERIFIER_BATCH_SIZE", "500"))
MATCH_WINDOW_SEC = int(os.environ.get("VERIFIER_MATCH_WINDOW_SEC", "90"))
GRAPHQL_TIMEOUT = int(os.environ.get("VERIFIER_GRAPHQL_TIMEOUT", "30"))
MAX_BATCHES = int(os.environ.get("VERIFIER_MAX_BATCHES", "20"))


def get_conn():
    return psycopg2.connect(
        host=env("POSTGRES_HOST"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=env("POSTGRES_DB"),
        user=env("POSTGRES_USER"),
        password=env("POSTGRES_PASSWORD"),
        sslmode=os.environ.get("POSTGRES_SSLMODE", "disable"),
        connect_timeout=int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "10")),
    )


def ensure_schema(conn) -> None:
    """Add the block_creator column if it's missing. Idempotent."""
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE submissions "
            "ADD COLUMN IF NOT EXISTS block_creator TEXT"
        )
    conn.commit()


def _to_utc(dt: datetime) -> datetime:
    """Treat naive timestamps as UTC; convert aware ones to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    """ISO 8601 with explicit Z suffix, what archive-node-api expects."""
    return _to_utc(dt).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fetch_best_chain_blocks(start: datetime, end: datetime) -> List[Dict]:
    """Return best-chain blocks whose dateTime is in [start, end).

    Each entry: {"blockHeight": int, "creator": str, "stateHash": str,
                 "dateTime": datetime (UTC, aware)}.

    archive-node-api returns dateTime as a string of unix-millis or ISO; we
    parse defensively.
    """
    query = """
      query($from: DateTime!, $to: DateTime!) {
        blocks(query: {dateTime_gte: $from, dateTime_lt: $to, inBestChain: true}) {
          blockHeight
          creator
          stateHash
          dateTime
        }
      }
    """
    variables = {"from": _iso_z(start), "to": _iso_z(end)}
    r = requests.post(
        ARCHIVE_URL,
        json={"query": query, "variables": variables},
        timeout=GRAPHQL_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    raw = body.get("data", {}).get("blocks") or []
    parsed: List[Dict] = []
    for b in raw:
        b["dateTime"] = _parse_archive_datetime(b["dateTime"])
        parsed.append(b)
    return parsed


def _parse_archive_datetime(value) -> datetime:
    """archive-node-api returns dateTime as either ISO string or unix-millis
    string. Handle both."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    s = str(value)
    if s.isdigit():
        return datetime.fromtimestamp(int(s) / 1000.0, tz=timezone.utc)
    # ISO 8601 — replace trailing Z with +00:00 for fromisoformat
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def classify(
    row,
    blocks: List[Dict],
    window: timedelta,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Return (verified, validation_error, block_creator) for one row.

    Blocks must already be filtered to best-chain blocks anywhere near this
    row's submitted_at; we narrow to the window here.
    """
    submitted = _to_utc(row["submitted_at"])
    lo, hi = submitted - window, submitted + window
    nearby = [b for b in blocks if lo <= b["dateTime"] < hi]
    if not nearby:
        return False, "no-block-near-submission-time", None
    self_blocks = [b for b in nearby if b["creator"] == row["submitter"]]
    if self_blocks:
        return True, None, row["submitter"]
    # Pick the temporally closest block's creator for context
    closest = min(nearby, key=lambda b: abs(b["dateTime"] - submitted))
    return True, "submission-near-block-not-by-self", closest["creator"]


def process_batch() -> int:
    """Process one batch of unverified rows. Returns rows updated."""
    with get_conn() as conn:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, submitter, submitted_at
                FROM submissions
                WHERE verified IS NULL
                  AND submitted_at IS NOT NULL
                ORDER BY submitted_at ASC
                LIMIT %s
                """,
                (BATCH_SIZE,),
            )
            rows = cur.fetchall()
        if not rows:
            return 0

        window = timedelta(seconds=MATCH_WINDOW_SEC)
        min_t = _to_utc(min(r["submitted_at"] for r in rows)) - window
        max_t = _to_utc(max(r["submitted_at"] for r in rows)) + window
        log.info(
            "Fetched %d unverified rows, fetching best-chain blocks for [%s, %s)",
            len(rows),
            min_t.isoformat(),
            max_t.isoformat(),
        )

        blocks = fetch_best_chain_blocks(min_t, max_t)
        log.info("Archive returned %d best-chain blocks in the window", len(blocks))

        updates: List[Tuple[bool, Optional[str], Optional[str], int]] = []
        counts = {"verified_self": 0, "verified_near": 0, "rejected": 0}
        for row in rows:
            verified, err, creator = classify(row, blocks, window)
            updates.append((verified, err, creator, row["id"]))
            if verified and err is None:
                counts["verified_self"] += 1
            elif verified:
                counts["verified_near"] += 1
            else:
                counts["rejected"] += 1

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE submissions
                SET verified = %s,
                    validation_error = %s,
                    block_creator = %s
                WHERE id = %s
                """,
                updates,
                page_size=500,
            )
        conn.commit()
        log.info(
            "Batch complete: %(verified_self)d self-produced, "
            "%(verified_near)d near-canonical, %(rejected)d rejected",
            counts,
        )
        return len(updates)


def main() -> int:
    log.info(
        "verifier starting (archive=%s batch=%d match_window_sec=%d max_batches=%d)",
        ARCHIVE_URL,
        BATCH_SIZE,
        MATCH_WINDOW_SEC,
        MAX_BATCHES,
    )
    total = 0
    for i in range(MAX_BATCHES):
        try:
            n = process_batch()
        except Exception:
            log.exception("Batch %d failed", i + 1)
            return 1
        if n == 0:
            log.info("No more unverified rows; exiting after %d updates", total)
            break
        total += n
        time.sleep(1)
    else:
        log.info(
            "Hit MAX_BATCHES=%d; updated %d rows this run, more remain for next run",
            MAX_BATCHES,
            total,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
