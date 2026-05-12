"""Unit tests for the verifier module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import verifier


def _block(height, creator, ts, state_hash="3Nh"):
    return {
        "blockHeight": height,
        "creator": creator,
        "stateHash": state_hash,
        "dateTime": ts,
    }


WINDOW = timedelta(seconds=90)


def test_classify_self_produced():
    submitted = datetime(2026, 5, 12, 11, 36, 30, tzinfo=timezone.utc)
    row = {"submitter": "B62qA", "submitted_at": submitted}
    blocks = [_block(100, "B62qA", submitted - timedelta(seconds=10))]
    verified, err, creator = verifier.classify(row, blocks, WINDOW)
    assert verified is True
    assert err is None
    assert creator == "B62qA"


def test_classify_near_canonical_other_creator():
    submitted = datetime(2026, 5, 12, 11, 36, 30, tzinfo=timezone.utc)
    row = {"submitter": "B62qA", "submitted_at": submitted}
    blocks = [
        _block(100, "B62qZ", submitted - timedelta(seconds=60)),
        _block(101, "B62qY", submitted + timedelta(seconds=20)),
    ]
    verified, err, creator = verifier.classify(row, blocks, WINDOW)
    assert verified is True
    assert err == "submission-near-block-not-by-self"
    # The temporally closest block's creator is reported
    assert creator == "B62qY"


def test_classify_no_canonical_in_window():
    submitted = datetime(2026, 5, 12, 11, 36, 30, tzinfo=timezone.utc)
    row = {"submitter": "B62qA", "submitted_at": submitted}
    # Block is way outside the 90s window
    blocks = [_block(100, "B62qZ", submitted - timedelta(minutes=20))]
    verified, err, creator = verifier.classify(row, blocks, WINDOW)
    assert verified is False
    assert err == "no-block-near-submission-time"
    assert creator is None


def test_classify_naive_submitted_at_treated_as_utc():
    naive = datetime(2026, 5, 12, 11, 36, 30)  # no tzinfo
    row = {"submitter": "B62qA", "submitted_at": naive}
    blocks = [_block(100, "B62qA",
                    datetime(2026, 5, 12, 11, 36, 25, tzinfo=timezone.utc))]
    verified, err, creator = verifier.classify(row, blocks, WINDOW)
    assert verified is True
    assert err is None
    assert creator == "B62qA"


def test_parse_archive_datetime_unix_millis_int():
    target = datetime(2026, 5, 12, 11, 32, 0, tzinfo=timezone.utc)
    millis = int(target.timestamp() * 1000)
    assert verifier._parse_archive_datetime(millis) == target


def test_parse_archive_datetime_unix_millis_string():
    target = datetime(2026, 5, 12, 11, 32, 0, tzinfo=timezone.utc)
    millis = str(int(target.timestamp() * 1000))
    assert verifier._parse_archive_datetime(millis) == target


def test_parse_archive_datetime_iso():
    ts = verifier._parse_archive_datetime("2026-05-12T11:32:00Z")
    assert ts == datetime(2026, 5, 12, 11, 32, 0, tzinfo=timezone.utc)


def test_fetch_canonical_blocks_passes_iso_window(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "blocks": [
                {
                    "blockHeight": 100,
                    "creator": "B62qA",
                    "stateHash": "3Nh",
                    "dateTime": "2026-05-12T11:32:00.000Z",
                }
            ]
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(verifier.requests, "post", mock_post)

    start = datetime(2026, 5, 12, 11, 30, tzinfo=timezone.utc)
    end = datetime(2026, 5, 12, 11, 40, tzinfo=timezone.utc)
    blocks = verifier.fetch_best_chain_blocks(start, end)
    assert len(blocks) == 1
    assert blocks[0]["blockHeight"] == 100
    assert blocks[0]["creator"] == "B62qA"
    assert blocks[0]["dateTime"] == datetime(
        2026, 5, 12, 11, 32, tzinfo=timezone.utc
    )

    _, kwargs = mock_post.call_args
    variables = kwargs["json"]["variables"]
    assert variables["from"].startswith("2026-05-12T11:30:00")
    assert variables["from"].endswith("Z")
    assert variables["to"].startswith("2026-05-12T11:40:00")


def test_fetch_canonical_blocks_raises_on_graphql_errors(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {"errors": [{"message": "boom"}]}
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(
        verifier.requests, "post", MagicMock(return_value=mock_response)
    )
    try:
        verifier.fetch_best_chain_blocks(
            datetime(2026, 5, 12, tzinfo=timezone.utc),
            datetime(2026, 5, 13, tzinfo=timezone.utc),
        )
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
