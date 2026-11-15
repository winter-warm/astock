from copy import deepcopy

import pytest

from astock.validation import summarize_market


SYMBOLS = ["600000.SH", "000001.SZ", "510300.SH", "159915.SZ"]


def observations():
    # Synthetic evidence tests the acceptance gate, not a market connection.
    return [{"offset_seconds": i * 5, "in_session": True, "ok": True,
             "quotes": [{"symbol": s, "age": 2, "advanced": i > 0} for s in SYMBOLS]}
            for i in range(721)]


def test_full_hour_coverage_and_report():
    report = summarize_market(observations(), SYMBOLS, 3601)
    assert report["one_hour_session_passed"]
    assert report["observed_span_seconds"] == 3600
    assert report["refresh_interval_seconds"]["mean"] == 5
    assert report["symbols"]["510300.SH"]["missing"] == 0
    assert report["error_rate"] == 0


@pytest.mark.parametrize("problem", ["missing", "duplicate", "empty", "future", "stale", "failure", "closed", "frozen", "gap", "short"])
def test_incomplete_evidence_cannot_pass(problem):
    samples = deepcopy(observations())
    sample = samples[300]
    if problem == "missing":
        sample["quotes"].pop()
    elif problem == "duplicate":
        sample["quotes"][-1] = deepcopy(sample["quotes"][0])
    elif problem == "empty":
        sample["quotes"] = []
    elif problem in ("future", "stale"):
        sample["quotes"][0]["age"] = -1 if problem == "future" else 16
    elif problem == "failure":
        sample.update(ok=False, quotes=[])
    elif problem == "closed":
        sample["in_session"] = False
    elif problem == "frozen":
        for row in samples:
            row["quotes"][0]["advanced"] = False
    elif problem == "gap":
        del samples[300:310]
    elif problem == "short":
        samples.pop()
    report = summarize_market(samples, SYMBOLS, 3601)
    assert not report["one_hour_session_passed"]
    if problem in ("missing", "duplicate", "empty", "failure"):
        assert report["errors"] == 1


def test_empty_and_partial_responses_are_not_connectivity_success():
    assert not summarize_market([], SYMBOLS, 3600)["connectivity_passed"]
    samples = observations()[:1]
    samples[0]["quotes"].pop()
    report = summarize_market(samples, SYMBOLS, 1)
    assert not report["connectivity_passed"]
    assert report["symbols"][SYMBOLS[-1]]["missing"] == 1
