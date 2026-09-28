import asyncio
from datetime import UTC, datetime

import pytest

from uptime_graphql.config import Settings
from uptime_graphql.db import percent
from uptime_graphql.schema import build_schema

from .conftest import ALWAYS, END, LAST_DAY, SUBMITS_ONLY, UNSCORED

END_ISO = datetime.fromtimestamp(END, tz=UTC).isoformat()

UPTIME = """
query ($key: String!) {
  blockProducer(publicKey: $key) {
    publicKey
    day: uptime(window: DAY) { percent points batches windowStart windowEnd lastPointAt }
    week: uptime(window: WEEK) { percent points batches }
    month: uptime(window: MONTH) { percent points batches }
  }
}
"""


def test_uptime_every_batch_counts_each_batch_once(gql):
    # Two `nodes` rows for one key (the one with the most points counts)
    # and a leftover point in the excluded batch: still 100%.
    bp = gql(UPTIME, key=ALWAYS)["data"]["blockProducer"]
    assert bp["day"] == {
        "percent": 100.0,
        "points": 71,
        "batches": 71,
        "windowStart": datetime.fromtimestamp(END - 86400, tz=UTC).isoformat(),
        "windowEnd": END_ISO,
        "lastPointAt": END_ISO,
    }
    assert bp["week"] == {"percent": 100.0, "points": 503, "batches": 503}
    assert bp["month"] == {"percent": 100.0, "points": 2159, "batches": 2159}


def test_uptime_last_day_only_is_truncated_like_the_scoreboard(gql):
    bp = gql(UPTIME, key=LAST_DAY)["data"]["blockProducer"]
    assert bp["day"]["percent"] == 100.0
    assert bp["week"] == {"percent": 14.11, "points": 71, "batches": 503}
    assert bp["month"] == {"percent": 3.28, "points": 71, "batches": 2159}


def test_uptime_without_points(gql):
    bp = gql(UPTIME, key=SUBMITS_ONLY)["data"]["blockProducer"]
    assert bp["day"]["percent"] == 0.0
    assert bp["day"]["lastPointAt"] is None


def test_is_up_uses_last_submission(gql):
    query = """
    query ($a: String!, $b: String!) {
      a: blockProducer(publicKey: $a) { isUp lastSubmissionAt officialScore { scorePercent applicationStatus } }
      b: blockProducer(publicKey: $b) { isUp wide: isUp(withinMinutes: 180) officialScore { score } }
    }
    """
    data = gql(query, a=SUBMITS_ONLY, b=UNSCORED)["data"]
    assert data["a"]["isUp"] is True
    assert data["a"]["lastSubmissionAt"].endswith("+00:00")
    assert data["a"]["officialScore"] == {"scorePercent": 0.0, "applicationStatus": False}
    assert data["b"] == {"isUp": False, "wide": True, "officialScore": None}


def test_is_up_rejects_bad_window(gql):
    result = gql('query ($k: String!) { blockProducer(publicKey: $k) { isUp(withinMinutes: 0) } }', k=SUBMITS_ONLY)
    assert "withinMinutes" in result["errors"][0]["message"]


def test_unknown_key_is_null(gql):
    assert gql(UPTIME, key="B62qnobody")["data"]["blockProducer"] is None


def test_pagination_and_filter(gql):
    page = """
    query ($after: String, $status: Boolean) {
      blockProducers(first: 2, after: $after, applicationStatus: $status) {
        items { publicKey } nextCursor
      }
    }
    """
    first = gql(page)["data"]["blockProducers"]
    assert [i["publicKey"] for i in first["items"]] == [ALWAYS, LAST_DAY]
    assert first["nextCursor"] == LAST_DAY
    second = gql(page, after=first["nextCursor"])["data"]["blockProducers"]
    assert second == {"items": [{"publicKey": SUBMITS_ONLY}], "nextCursor": None}
    rejected = gql(page, status=False)["data"]["blockProducers"]
    assert rejected["items"] == [{"publicKey": SUBMITS_ONLY}]


def test_list_with_uptime_batches_queries(gql):
    query = "{ blockProducers(first: 2) { items { publicKey isUp uptime(window: WEEK) { percent } } } }"
    items = gql(query)["data"]["blockProducers"]["items"]
    assert [i["uptime"]["percent"] for i in items] == [100.0, 14.11]


def test_page_size_limit(gql):
    result = gql("{ blockProducers(first: 3) { nextCursor } }")
    assert "first must be between 1 and 2" in result["errors"][0]["message"]


def test_meta(gql):
    assert gql("{ meta { lastBatchEnd isUpWindowMinutes } }")["data"]["meta"] == {
        "lastBatchEnd": END_ISO,
        "isUpWindowMinutes": 40,
    }


def test_depth_limit():
    # Depth counts from 0 at the root field: blockProducers.items.uptime.percent is 3.
    schema = build_schema(Settings(conninfo="", max_query_depth=2))
    result = asyncio.run(schema.execute("{ blockProducers { items { uptime(window: DAY) { percent } } } }"))
    assert result.data is None
    assert "exceeds maximum operation depth" in result.errors[0].message


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


@pytest.mark.parametrize(
    "points,batches,expected",
    [(0, 0, None), (0, 10, 0.0), (1, 3, 33.33), (2, 3, 66.66), (3, 3, 100.0)],
)
def test_percent_truncates(points, batches, expected):
    assert percent(points, batches) == expected


def test_settings_require_postgres():
    with pytest.raises(RuntimeError, match="POSTGRES_HOST"):
        Settings.from_env({"POSTGRES_DB": "x", "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x"})
