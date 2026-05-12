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
