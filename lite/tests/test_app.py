"""Unit tests for the navigator API."""

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import app as appmod


def _mock_conn(rows):
    """Build a context-managing mock that mimics psycopg2 connection+cursor."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    cur.execute = MagicMock()
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


@pytest.fixture
def client(monkeypatch):
    appmod.app.config.update(TESTING=True)
    monkeypatch.delenv("WHITELIST", raising=False)
    return appmod.app.test_client()


def test_healthz_ok(client, monkeypatch):
    conn, _ = _mock_conn([(1,)])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_healthz_db_error(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(appmod, "get_conn", boom)
    resp = client.get("/healthz")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "db down" in body["error"]


def test_submitters_returns_rows(client, monkeypatch):
    rows = [
        {
            "submitter": "B62qA",
            "submissions": 10,
            "last_seen": datetime(2026, 5, 12, 10, 0, 0),
            "first_seen": datetime(2026, 5, 12, 9, 0, 0),
            "valid": 9,
            "invalid": 1,
        }
    ]
    conn, cur = _mock_conn(rows)
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/submitters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["submitter"] == "B62qA"
    assert data[0]["last_seen"] == "2026-05-12T10:00:00"

    sql, params = cur.execute.call_args[0]
    assert "GROUP BY submitter" in sql
    assert params == []


def test_submitters_whitelist_filters(client, monkeypatch):
    monkeypatch.setenv("WHITELIST", "B62qA, B62qB")
    conn, cur = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    client.get("/api/submitters")
    sql, params = cur.execute.call_args[0]
    assert "submitter = ANY(%s)" in sql
    assert params == [["B62qA", "B62qB"]]


def test_submitter_detail(client, monkeypatch):
    rows = [
        {
            "id": 1,
            "submitted_at": datetime(2026, 5, 12, 10, 0, 0),
            "block_hash": "3Nhash",
            "state_hash": "3Nstate",
            "parent": "3Nparent",
            "height": 100,
            "slot": 200,
            "validation_error": None,
            "verified": True,
            "remote_addr": "1.2.3.4",
            "peer_id": "peer",
            "built_with_commit_sha": "abc",
        }
    ]
    conn, _ = _mock_conn(rows)
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/submitter/B62qA")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data[0]["height"] == 100
    assert data[0]["submitted_at"] == "2026-05-12T10:00:00"


def test_submitter_detail_blocked_by_whitelist(client, monkeypatch):
    monkeypatch.setenv("WHITELIST", "B62qOther")
    monkeypatch.setattr(appmod, "get_conn", lambda: _mock_conn([])[0])

    resp = client.get("/api/submitter/B62qA")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "not in whitelist"}


def test_summary(client, monkeypatch):
    rows = [{"day": "2026-05-12", "submitter": "B62qA", "submissions": 5}]
    conn, _ = _mock_conn(rows)
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/summary")
    assert resp.status_code == 200
    assert resp.get_json() == rows


def test_uptime_returns_coverage(client, monkeypatch):
    rows = [
        {"bucket_start": datetime(2026, 5, 12, 9, 0, 0), "submissions": 1, "chain_verified": 1},
        {"bucket_start": datetime(2026, 5, 12, 9, 5, 0), "submissions": 0, "chain_verified": 0},
        {"bucket_start": datetime(2026, 5, 12, 9, 10, 0), "submissions": 2, "chain_verified": 0},
        {"bucket_start": datetime(2026, 5, 12, 9, 15, 0), "submissions": 0, "chain_verified": 0},
    ]
    conn, cur = _mock_conn(rows)
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/uptime/B62qA?window=1&bucket_minutes=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pubkey"] == "B62qA"
    assert data["window_hours"] == 1
    assert data["bucket_minutes"] == 5
    assert data["coverage_pct"] == 50.0  # 2 of 4 buckets had submissions
    assert data["chain_verified_pct"] == 25.0  # 1 of 4 buckets had a verified one
    assert data["buckets"][0]["bucket_start"] == "2026-05-12T09:00:00"

    sql, params = cur.execute.call_args[0]
    assert "generate_series" in sql
    assert "LOCALTIMESTAMP" in sql
    assert "LEFT JOIN submissions" in sql
    assert params == (1, 5, "B62qA")


def test_uptime_clamps_window(client, monkeypatch):
    conn, _ = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/uptime/B62qA?window=9999")
    assert resp.status_code == 200
    assert resp.get_json()["window_hours"] == 168  # clamped to max

    resp = client.get("/api/uptime/B62qA?window=0")
    assert resp.status_code == 200
    assert resp.get_json()["window_hours"] == 1  # clamped to min


def test_uptime_invalid_window(client, monkeypatch):
    conn, _ = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/uptime/B62qA?window=foo")
    assert resp.status_code == 400
    assert "window" in resp.get_json()["error"]


def test_uptime_blocked_by_whitelist(client, monkeypatch):
    monkeypatch.setenv("WHITELIST", "B62qOther")
    monkeypatch.setattr(appmod, "get_conn", lambda: _mock_conn([])[0])

    resp = client.get("/api/uptime/B62qA")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "not in whitelist"}


# ---- /api/leaderboard --------------------------------------------------

def _decimal(s):
    from decimal import Decimal
    return Decimal(s)


def test_leaderboard_defaults_to_production_constants(client, monkeypatch):
    rows = [
        {"block_producer_key": "B62qA", "score": 6259, "score_percent": _decimal("99.71"), "surveys": 6480},
    ]
    conn, cur = _mock_conn(rows)
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["uptime_days"] == 90
    assert body["survey_interval_minutes"] == 20
    assert body["require_verified"] is True

    sql, params = cur.execute.call_args[0]
    # Default constants flow into the SQL params
    assert params == [90, 20]
    # Strict mode injects the verified filter
    assert "s.verified IS TRUE" in sql
    # Production score formula
    assert "COUNT(DISTINCT b.bucket_start)" in sql
    assert "score::decimal * 100.0" in sql
    assert "TRUNC" in sql

    [row] = body["rows"]
    assert row["block_producer_key"] == "B62qA"
    assert row["score"] == 6259
    # Decimal converted to float for JSON
    assert row["score_percent"] == 99.71
    assert row["surveys"] == 6480


def test_leaderboard_require_verified_false_omits_filter(client, monkeypatch):
    conn, cur = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    client.get("/api/leaderboard?require_verified=false")
    sql, _ = cur.execute.call_args[0]
    assert "s.verified IS TRUE" not in sql


def test_leaderboard_whitelist_filters(client, monkeypatch):
    monkeypatch.setenv("WHITELIST", "B62qA,B62qB")
    conn, cur = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    client.get("/api/leaderboard")
    sql, params = cur.execute.call_args[0]
    assert "s.submitter = ANY(%s)" in sql
    assert params[-1] == ["B62qA", "B62qB"]


def test_leaderboard_clamps_window(client, monkeypatch):
    conn, cur = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    client.get("/api/leaderboard?uptime_days=9999&survey_interval_minutes=99999")
    body = (
        client.get("/api/leaderboard?uptime_days=9999&survey_interval_minutes=99999")
        .get_json()
    )
    assert body["uptime_days"] == 365  # clamped to max
    assert body["survey_interval_minutes"] == 1440  # clamped to max

    body = (
        client.get("/api/leaderboard?uptime_days=0&survey_interval_minutes=0")
        .get_json()
    )
    assert body["uptime_days"] == 1
    assert body["survey_interval_minutes"] == 1


def test_leaderboard_invalid_params(client, monkeypatch):
    conn, _ = _mock_conn([])
    monkeypatch.setattr(appmod, "get_conn", lambda: conn)

    resp = client.get("/api/leaderboard?uptime_days=foo")
    assert resp.status_code == 400
    assert "uptime_days" in resp.get_json()["error"]

    resp = client.get("/api/leaderboard?survey_interval_minutes=bar")
    assert resp.status_code == 400
    assert "survey_interval_minutes" in resp.get_json()["error"]
