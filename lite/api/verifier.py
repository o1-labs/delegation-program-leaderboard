"""One-shot verifier — cross-checks submissions against the canonical chain.

Reads rows in `submissions` where `verified IS NULL`, queries archive-node-api
GraphQL for the canonical blocks in the same height range, and updates each
row with:

- `verified=true` when the row's (height, state_hash) matches a canonical block
- `verified=false` + `validation_error` set, otherwise
- `block_creator` recording who actually produced the canonical block at that
  height (NULL if no canonical block exists at that height yet)

Designed to be invoked from a Kubernetes CronJob — runs once and exits. Safe
to run concurrently or on overlapping windows; the WHERE clause makes the
work idempotent.
"""

import logging
import os
import sys
import time
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
HEIGHT_BUCKET = int(os.environ.get("VERIFIER_HEIGHT_BUCKET", "100"))
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


def fetch_canonical_blocks(min_h: int, max_h: int) -> Dict[int, Dict[str, str]]:
    """Returns {height: {stateHash: creator, ...}, ...} for the canonical chain
    between [min_h, max_h] inclusive."""
    query = """
      query($from: Int!, $to: Int!) {
        blocks(query: {blockHeight_gte: $from, blockHeight_lt: $to, canonical: true}) {
          blockHeight
          creator
          stateHash
        }
      }
    """
    variables = {"from": min_h, "to": max_h + 1}
    r = requests.post(
        ARCHIVE_URL,
        json={"query": query, "variables": variables},
        timeout=GRAPHQL_TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    blocks = body.get("data", {}).get("blocks") or []
    out: Dict[int, Dict[str, str]] = {}
    for b in blocks:
        out.setdefault(b["blockHeight"], {})[b["stateHash"]] = b["creator"]
    return out


def classify(row, blocks_at_height: Dict[str, str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Return (verified, validation_error, block_creator) for one submission row."""
    if not blocks_at_height:
        return False, "no-canonical-block-at-height", None
    state_hash = row["state_hash"]
    creator = blocks_at_height.get(state_hash)
    if creator is not None:
        return True, None, creator
    return False, "state-hash-not-on-canonical-chain", None


def process_batch() -> int:
    """Process one batch of unverified rows. Returns rows updated."""
    with get_conn() as conn:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, submitter, state_hash, height
                FROM submissions
                WHERE verified IS NULL
                  AND state_hash IS NOT NULL
                  AND height IS NOT NULL
                ORDER BY height ASC
                LIMIT %s
                """,
                (BATCH_SIZE,),
            )
            rows = cur.fetchall()
        if not rows:
            return 0

        min_h = min(r["height"] for r in rows)
        max_h = max(r["height"] for r in rows)
        log.info(
            "Fetched %d unverified rows, height range [%d, %d]",
            len(rows),
            min_h,
            max_h,
        )

        canonical: Dict[int, Dict[str, str]] = {}
        h = min_h
        while h <= max_h:
            window_end = min(h + HEIGHT_BUCKET - 1, max_h)
            window = fetch_canonical_blocks(h, window_end)
            canonical.update(window)
            log.info(
                "Archive returned %d canonical blocks for [%d, %d]",
                sum(len(v) for v in window.values()),
                h,
                window_end,
            )
            h = window_end + 1

        updates: List[Tuple[bool, Optional[str], Optional[str], int]] = []
        verified_count = 0
        unverified_count = 0
        for row in rows:
            verified, err, creator = classify(row, canonical.get(row["height"], {}))
            updates.append((verified, err, creator, row["id"]))
            if verified:
                verified_count += 1
            else:
                unverified_count += 1

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
            "Batch complete: %d verified, %d unverified",
            verified_count,
            unverified_count,
        )
        return len(updates)


def main() -> int:
    log.info(
        "verifier starting (archive=%s batch=%d bucket=%d max_batches=%d)",
        ARCHIVE_URL,
        BATCH_SIZE,
        HEIGHT_BUCKET,
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
