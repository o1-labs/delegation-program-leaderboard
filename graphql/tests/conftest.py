from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from starlette.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from uptime_graphql.app import create_app
from uptime_graphql.config import Settings

BATCH = 1200  # 20-minute survey interval
DAY_BATCHES = 72
# End of the latest batch. Aligned but not tied to now(): uptime is anchored
# on the batches, only isUp depends on the clock.
END = int(datetime.now(UTC).timestamp()) // BATCH * BATCH
# Batch index k covers [END - (k + 1) * BATCH, END - k * BATCH]; k = 0 is the latest.
EXCLUDED_K = 5
MONTH_BATCHES = 30 * DAY_BATCHES

ALWAYS = "B62qalways"  # a point in every batch, from two `nodes` rows
LAST_DAY = "B62qlastday"  # points only in the last day
SUBMITS_ONLY = "B62qsubmitsonly"  # scored row, no points, recent submission
UNSCORED = "B62qunscored"  # not in nodes, last submission 2 hours ago


@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        dsn = container.get_connection_url()
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute((Path(__file__).parent / "schema.sql").read_text())
            seed(conn)
        yield container


def seed(conn):
    batch_ids = {}
    with conn.cursor() as cur:
        for k in range(31 * DAY_BATCHES):
            cur.execute(
                "INSERT INTO bot_logs (files_processed, batch_start_epoch, batch_end_epoch)"
                " VALUES (%s, %s, %s) RETURNING id",
                (-1 if k == EXCLUDED_K else 10, END - (k + 1) * BATCH, END - k * BATCH),
            )
            batch_ids[k] = cur.fetchone()[0]

        def node(key, status, score=None, score_percent=None):
            cur.execute(
                "INSERT INTO nodes (block_producer_key, updated_at, score, score_percent,"
                " application_status) VALUES (%s, now(), %s, %s, %s) RETURNING id",
                (key, score, score_percent, status),
            )
            return cur.fetchone()[0]

        def points(node_id, ks):
            cur.executemany(
                "INSERT INTO points (node_id, bot_log_id) VALUES (%s, %s)",
                [(node_id, batch_ids[k]) for k in ks],
            )

        always_a = node(ALWAYS, True, 2159, 100)
        always_b = node(ALWAYS, True)
        # A point in the excluded batch too: a correction deletes it, but the
        # query must not count it even if it is still there.
        points(always_a, range(31 * DAY_BATCHES))
        points(always_b, range(10))
        points(node(LAST_DAY, True, 71, 3.28), range(DAY_BATCHES))
        node(SUBMITS_ONLY, False, 0, 0)

        now = datetime.now(UTC).replace(tzinfo=None)

        def submission(key, at):
            cur.execute(
                "INSERT INTO submissions (submitted_at_date, submitted_at, submitter) VALUES (%s, %s, %s)",
                (at.date(), at, key),
            )

        submission(SUBMITS_ONLY, now - timedelta(minutes=60))
        submission(SUBMITS_ONLY, now - timedelta(minutes=10))
        submission(UNSCORED, now - timedelta(hours=2))


@pytest.fixture(scope="session")
def settings(pg):
    env = {
        "POSTGRES_HOST": pg.get_container_host_ip(),
        "POSTGRES_PORT": str(pg.get_exposed_port(5432)),
        "POSTGRES_DB": pg.dbname,
        "POSTGRES_USER": pg.username,
        "POSTGRES_PASSWORD": pg.password,
        "MAX_PAGE_SIZE": "2",
    }
    return Settings.from_env(env)


@pytest.fixture(scope="session")
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def gql(client):
    def run(query, **variables):
        response = client.post("/graphql", json={"query": query, "variables": variables})
        assert response.status_code == 200, response.text
        return response.json()

    return run
