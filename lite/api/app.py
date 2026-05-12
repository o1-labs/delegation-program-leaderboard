"""Minimal uptime-navigator API.

Reads directly from the `submissions` table populated by uptime-service-backend
and exposes a small read-only HTTP surface. Optional comma-separated WHITELIST
env var filters every query to a set of submitter public keys.
"""

import os

import psycopg2
from flask import Flask, jsonify, send_from_directory
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
               COUNT(*) FILTER (WHERE validation_error IS NOT NULL) AS invalid
        FROM submissions
        {where}
        GROUP BY submitter
        ORDER BY submissions DESC
    """
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return jsonify(_row_dates_iso(rows, "last_seen", "first_seen"))


@app.get("/api/submitter/<pubkey>")
def submitter(pubkey):
    keys = whitelist()
    if keys is not None and pubkey not in keys:
        return jsonify(error="not in whitelist"), 404
    sql = """
        SELECT id, submitted_at, block_hash, state_hash, parent,
               height, slot, validation_error, verified, remote_addr,
               peer_id, built_with_commit_sha
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
