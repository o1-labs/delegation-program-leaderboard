"""Minimal uptime-navigator API.

Reads directly from the `submissions` table populated by uptime-service-backend
and exposes a small read-only HTTP surface. Optional comma-separated WHITELIST
env var filters every query to a set of submitter public keys.
"""

import os

import psycopg2
from flask import Flask, jsonify, request, send_from_directory
from psycopg2.extras import RealDictCursor

WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")

app = Flask(__name__, static_folder=WEB_ROOT, static_url_path="")


def get_conn():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        sslmode=os.environ.get("POSTGRES_SSLMODE", "disable"),
        connect_timeout=int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5")),
    )


def whitelist():
    raw = os.environ.get("WHITELIST", "").strip()
    if not raw:
        return None
    return [k.strip() for k in raw.split(",") if k.strip()]


def _row_dates_iso(rows, *fields):
    for r in rows:
        for f in fields:
            if r.get(f) is not None:
                r[f] = r[f].isoformat()
    return rows


@app.get("/healthz")
def healthz():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify(status="ok"), 200
    except Exception as e:
        return jsonify(status="error", error=str(e)), 500


@app.get("/api/submitters")
def submitters():
    keys = whitelist()
    where = "WHERE 1=1"
    params = []
    if keys is not None:
        where += " AND submitter = ANY(%s)"
        params.append(keys)
    sql = f"""
        SELECT submitter,
               COUNT(*) AS submissions,
               MAX(submitted_at) AS last_seen,
               MIN(submitted_at) AS first_seen,
               COUNT(*) FILTER (WHERE validation_error IS NULL) AS valid,
               COUNT(*) FILTER (WHERE validation_error IS NOT NULL) AS invalid,
               COUNT(*) FILTER (WHERE verified IS TRUE) AS chain_verified,
               COUNT(*) FILTER (WHERE verified IS FALSE) AS chain_rejected,
               COUNT(*) FILTER (WHERE verified IS NULL) AS chain_pending,
               COUNT(*) FILTER (WHERE block_creator = submitter) AS blocks_produced,
               MAX(height) AS max_height
        FROM submissions
        {where}
        GROUP BY submitter
        ORDER BY submissions DESC
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return jsonify(_row_dates_iso(rows, "last_seen", "first_seen"))


@app.get("/api/uptime/<pubkey>")
def uptime(pubkey):
    keys = whitelist()
    if keys is not None and pubkey not in keys:
        return jsonify(error="not in whitelist"), 404
    try:
        window_hours = int(request.args.get("window", "24"))
    except (TypeError, ValueError):
        return jsonify(error="window must be an integer (hours)"), 400
    window_hours = max(1, min(window_hours, 168))
    bucket_minutes = int(request.args.get("bucket_minutes", "5"))
    bucket_minutes = max(1, min(bucket_minutes, 60))

    sql = """
        WITH params AS (
            SELECT NOW() AS now_at,
                   NOW() - (%s || ' hours')::interval AS since_at,
                   (%s || ' minutes')::interval AS bucket
        ),
        buckets AS (
            SELECT generate_series(
                date_trunc('minute', (SELECT since_at FROM params)),
                date_trunc('minute', (SELECT now_at FROM params)),
                (SELECT bucket FROM params)
            ) AS bucket_start
        ),
        hits AS (
            SELECT date_trunc('minute', submitted_at) -
                   (EXTRACT(MINUTE FROM submitted_at)::int %% %s) * interval '1 minute'
                   AS bucket_start,
                   COUNT(*) AS submissions,
                   COUNT(*) FILTER (WHERE verified IS TRUE) AS chain_verified
            FROM submissions
            WHERE submitter = %s AND submitted_at >= (SELECT since_at FROM params)
            GROUP BY 1
        )
        SELECT buckets.bucket_start AS bucket_start,
               COALESCE(hits.submissions, 0) AS submissions,
               COALESCE(hits.chain_verified, 0) AS chain_verified
        FROM buckets LEFT JOIN hits USING (bucket_start)
        ORDER BY buckets.bucket_start ASC
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (window_hours, bucket_minutes, bucket_minutes, pubkey))
        rows = cur.fetchall()

    total_buckets = len(rows)
    hit_buckets = sum(1 for r in rows if r["submissions"] > 0)
    verified_buckets = sum(1 for r in rows if r["chain_verified"] > 0)
    coverage_pct = round(100.0 * hit_buckets / total_buckets, 2) if total_buckets else 0.0
    verified_pct = round(100.0 * verified_buckets / total_buckets, 2) if total_buckets else 0.0

    for r in rows:
        if r["bucket_start"] is not None:
            r["bucket_start"] = r["bucket_start"].isoformat()
    return jsonify({
        "pubkey": pubkey,
        "window_hours": window_hours,
        "bucket_minutes": bucket_minutes,
        "coverage_pct": coverage_pct,
        "chain_verified_pct": verified_pct,
        "buckets": rows,
    })


@app.get("/api/submitter/<pubkey>")
def submitter(pubkey):
    keys = whitelist()
    if keys is not None and pubkey not in keys:
        return jsonify(error="not in whitelist"), 404
    sql = """
        SELECT id, submitted_at, block_hash, state_hash, parent,
               height, slot, validation_error, verified, block_creator,
               remote_addr, peer_id, built_with_commit_sha
        FROM submissions
        WHERE submitter = %s
        ORDER BY submitted_at DESC
        LIMIT 100
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (pubkey,))
        rows = cur.fetchall()
    return jsonify(_row_dates_iso(rows, "submitted_at"))


@app.get("/api/summary")
def summary():
    keys = whitelist()
    where = "WHERE 1=1"
    params = []
    if keys is not None:
        where += " AND submitter = ANY(%s)"
        params.append(keys)
    sql = f"""
        SELECT submitted_at_date::text AS day,
               submitter,
               COUNT(*) AS submissions
        FROM submissions
        {where}
        GROUP BY day, submitter
        ORDER BY day DESC, submissions DESC
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return jsonify(rows)


@app.get("/")
def root():
    return send_from_directory(WEB_ROOT, "index.html")
