import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from uptime_graphql.app import create_app
from uptime_graphql.config import Settings
from uptime_graphql.db import percent
from uptime_graphql.schema import build_schema

from .conftest import ACTIVITY_FROM, ALWAYS, END, FLAKY, LAST_DAY, SHUTDOWN, SUBMITS_ONLY, UNSCORED

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
    result = gql(
        "query ($k: String!) { blockProducer(publicKey: $k) { isUp(withinMinutes: 0) } }", k=SUBMITS_ONLY
    )
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
    keys, after = [], None
    while True:
        result = gql(page, after=after)["data"]["blockProducers"]
        keys += [i["publicKey"] for i in result["items"]]
        after = result["nextCursor"]
        if after is None:
            break
        assert after == keys[-1]
    assert keys == [ALWAYS, FLAKY, LAST_DAY, SHUTDOWN, SUBMITS_ONLY]
    rejected = gql(page, status=False)["data"]["blockProducers"]
    assert rejected["items"] == [{"publicKey": SUBMITS_ONLY}]


def test_list_with_uptime_batches_queries(gql):
    query = "{ blockProducers(first: 2) { items { publicKey isUp uptime(window: WEEK) { percent } } } }"
    items = gql(query)["data"]["blockProducers"]["items"]
    assert [i["uptime"]["percent"] for i in items] == [100.0, 14.31]


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


ACTIVITY = """
query ($key: String!, $from: DateTime!, $to: DateTime!, $bucket: BucketSize) {
  blockProducer(publicKey: $key) {
    activity(from: $from, to: $to, bucket: $bucket) {
      from to bucket
      buckets { start end submissions acceptedSubmissions failedSubmissions batches points percent }
      totals {
        submissions acceptedSubmissions failedSubmissions batches points percent
        bucketsWithSubmissions bucketCount
      }
      silences { start end minutes openEnded }
      longestSilence { minutes openEnded }
    }
  }
}
"""


def iso(epoch):
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def activity(gql, key, frm=ACTIVITY_FROM, to=END, bucket="HOUR"):
    result = gql(ACTIVITY, key=key, **{"from": iso(frm), "to": iso(to), "bucket": bucket})
    assert "errors" not in result, result["errors"]
    return result["data"]["blockProducer"]["activity"]


def bucket(start, submissions, accepted, failed, batches, points):
    return {
        "start": iso(start),
        "end": iso(start + 3600),
        "submissions": submissions,
        "acceptedSubmissions": accepted,
        "failedSubmissions": failed,
        "batches": batches,
        "points": points,
        "percent": percent(points, batches),
    }


def test_activity_shutdown_node(gql):
    # Same 2-day uptime as the flaky node, but one open-ended silence.
    a = activity(gql, SHUTDOWN)
    assert (a["from"], a["to"], a["bucket"]) == (iso(ACTIVITY_FROM), iso(END), "HOUR")
    assert len(a["buckets"]) == 48
    assert a["buckets"][0] == bucket(ACTIVITY_FROM, 12, 12, 0, 3, 3)
    assert a["buckets"][30] == bucket(ACTIVITY_FROM + 30 * 3600, 0, 0, 0, 3, 0)
    # The excluded batch starts in hour 46.
    assert a["buckets"][46]["batches"] == 2
    assert a["totals"] == {
        "submissions": 288,
        "acceptedSubmissions": 288,
        "failedSubmissions": 0,
        "batches": 143,
        "points": 72,
        "percent": 50.34,
        "bucketsWithSubmissions": 24,
        "bucketCount": 48,
    }
    last = END - 86400 - 300
    assert a["silences"] == [{"start": iso(last), "end": iso(END), "minutes": 1445, "openEnded": True}]
    assert a["longestSilence"] == {"minutes": 1445, "openEnded": True}


def test_activity_node_with_problems(gql):
    a = activity(gql, FLAKY)
    assert a["buckets"][0] == bucket(ACTIVITY_FROM, 12, 0, 12, 3, 0)
    assert a["buckets"][1] == bucket(ACTIVITY_FROM + 3600, 12, 12, 0, 3, 3)
    assert a["totals"] == {
        "submissions": 576,
        "acceptedSubmissions": 288,
        "failedSubmissions": 288,
        "batches": 143,
        "points": 72,
        "percent": 50.34,
        "bucketsWithSubmissions": 48,
        "bucketCount": 48,
    }
    assert a["silences"] == []
    assert a["longestSilence"] == {"minutes": 5, "openEnded": False}


def test_activity_day_buckets_and_no_submissions(gql):
    a = activity(gql, LAST_DAY, bucket="DAY")
    assert [(b["submissions"], b["batches"], b["points"]) for b in a["buckets"]] == [(0, 72, 0), (0, 71, 71)]
    # No submission at all: one silence over the whole range.
    assert a["silences"] == [
        {"start": iso(ACTIVITY_FROM), "end": iso(END), "minutes": 2880, "openEnded": True}
    ]


def test_activity_range_is_widened_to_buckets_and_ends_now(gql):
    now = datetime.now(UTC)
    a = activity(gql, SUBMITS_ONLY, frm=END - 1800, to=int((now + timedelta(days=1)).timestamp()))
    assert a["from"] == iso(END - 3600)
    assert datetime.fromisoformat(a["to"]) - now < timedelta(minutes=1)
    assert a["totals"]["submissions"] == 2


def test_activity_for_a_list_of_bps(gql):
    query = """
    query ($from: DateTime!, $to: DateTime!) {
      blockProducers(first: 2, after: "B62qflaky") {
        items { publicKey activity(from: $from, to: $to, bucket: DAY) { totals { points } longestSilence { minutes } } }
      }
    }
    """
    items = gql(query, **{"from": iso(ACTIVITY_FROM), "to": iso(END)})["data"]["blockProducers"]["items"]
    assert [(i["publicKey"], i["activity"]["totals"]["points"]) for i in items] == [
        (LAST_DAY, 71),
        (SHUTDOWN, 72),
    ]
    assert [i["activity"]["longestSilence"]["minutes"] for i in items] == [2880, 1445]


@pytest.mark.parametrize(
    "frm,to,bucket,error",
    [
        (END, END - 3600, "HOUR", "from must be before to"),
        (END - 93 * 86400, END, "DAY", "at most 92 days"),
        (END - 60 * 86400, END, "BATCH", "use a larger bucket"),
    ],
)
def test_activity_limits(gql, frm, to, bucket, error):
    result = gql(ACTIVITY, key=FLAKY, **{"from": iso(frm), "to": iso(to), "bucket": bucket})
    assert error in result["errors"][0]["message"]


def test_activity_request_bucket_budget(settings):
    # 2 BPs x 48 hourly buckets = 96 buckets; a budget of 95 refuses the request.
    tight = dataclasses.replace(settings, max_request_buckets=95)
    query = """
    query ($from: DateTime!, $to: DateTime!) {
      blockProducers(first: 2) { items { activity(from: $from, to: $to) { bucketCount: totals { bucketCount } } } }
    }
    """
    variables = {"from": iso(ACTIVITY_FROM), "to": iso(END)}
    with TestClient(create_app(tight)) as client:
        result = client.post("/graphql", json={"query": query, "variables": variables}).json()
    assert "more than 95 activity buckets" in result["errors"][0]["message"]


SCOREBOARD = """
query ($status: Boolean, $scoredOnly: Boolean! = true) {
  scoreboard(applicationStatus: $status, scoredOnly: $scoredOnly) {
    rank publicKey officialScore { score scorePercent applicationStatus }
  }
}
"""


def test_scoreboard_best_first(gql):
    board = gql(SCOREBOARD)["data"]["scoreboard"]
    assert [(e["rank"], e["publicKey"], e["officialScore"]["scorePercent"]) for e in board] == [
        (1, ALWAYS, 100.0),  # of its two `nodes` rows, the one with the score
        (2, LAST_DAY, 3.28),
        (3, SUBMITS_ONLY, 0.0),
    ]


def test_scoreboard_filters_and_shared_rank(gql):
    approved = gql(SCOREBOARD, status=True)["data"]["scoreboard"]
    assert [e["publicKey"] for e in approved] == [ALWAYS, LAST_DAY]
    everyone = gql(SCOREBOARD, scoredOnly=False)["data"]["scoreboard"]
    # Unscored BPs come last and share a rank.
    assert [(e["rank"], e["publicKey"]) for e in everyone[3:]] == [(4, FLAKY), (4, SHUTDOWN)]


def test_scoreboard_with_more_fields_per_bp(gql):
    query = """
    { scoreboard { publicKey blockProducer { officialScore { score } uptime(window: DAY) { percent } } } }
    """
    board = gql(query)["data"]["scoreboard"]
    assert [
        (e["blockProducer"]["officialScore"]["score"], e["blockProducer"]["uptime"]["percent"]) for e in board
    ] == [
        (2159, 100.0),
        (71, 100.0),
        (0, 0.0),
    ]
