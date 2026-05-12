"""Unit tests for the verifier module."""

import sys
from unittest.mock import MagicMock, patch

import verifier


def test_classify_match():
    row = {"state_hash": "3NHash", "height": 100, "submitter": "B62qSub"}
    blocks = {"3NHash": "B62qCreator"}
    verified, err, creator = verifier.classify(row, blocks)
    assert verified is True
    assert err is None
    assert creator == "B62qCreator"


def test_classify_state_hash_mismatch():
    row = {"state_hash": "3NHashFake", "height": 100, "submitter": "B62qSub"}
    blocks = {"3NHashReal": "B62qCreator"}
    verified, err, creator = verifier.classify(row, blocks)
    assert verified is False
    assert err == "state-hash-not-on-canonical-chain"
    assert creator is None


def test_classify_empty_height_bucket():
    row = {"state_hash": "3NHash", "height": 100, "submitter": "B62qSub"}
    verified, err, creator = verifier.classify(row, {})
    assert verified is False
    assert err == "no-canonical-block-at-height"
    assert creator is None


def test_fetch_canonical_blocks_buckets_by_height(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "blocks": [
                {"blockHeight": 100, "stateHash": "h100a", "creator": "B62q1"},
                {"blockHeight": 100, "stateHash": "h100b", "creator": "B62q2"},
                {"blockHeight": 101, "stateHash": "h101", "creator": "B62q1"},
            ]
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(verifier.requests, "post", mock_post)

    result = verifier.fetch_canonical_blocks(100, 101)
    assert result == {
        100: {"h100a": "B62q1", "h100b": "B62q2"},
        101: {"h101": "B62q1"},
    }
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["variables"] == {"from": 100, "to": 102}


def test_fetch_canonical_blocks_raises_on_graphql_errors(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {"errors": [{"message": "boom"}]}
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(
        verifier.requests, "post", MagicMock(return_value=mock_response)
    )

    try:
        verifier.fetch_canonical_blocks(100, 101)
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_fetch_canonical_blocks_handles_empty_response(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"blocks": None}}
    mock_response.raise_for_status = MagicMock()
    monkeypatch.setattr(
        verifier.requests, "post", MagicMock(return_value=mock_response)
    )
    assert verifier.fetch_canonical_blocks(100, 101) == {}
