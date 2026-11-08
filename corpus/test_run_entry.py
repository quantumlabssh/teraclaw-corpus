#!/usr/bin/env python3
"""Self-checks for the corpus harness. No dependencies; run in CI.

    python corpus/test_run_entry.py

A result whose assurance level is missing must fail the entry, never count as a
pass or a skip. This is the regression that let a broken run look clean.
"""

from __future__ import annotations

from run_entry import _level_from_result, _mismatch


def test_missing_assurance_is_an_error():
    assert _level_from_result({"status": "needs_review"}) == (
        "error",
        ["missing_level"],
    )
    assert _level_from_result({"receipt": {}}) == ("error", ["missing_level"])


def test_unknown_level_is_an_error():
    level, reasons = _level_from_result({"assurance": {"level": "ok"}})
    assert level == "error"
    assert "missing_level" in reasons


def test_known_level_and_reasons_are_read():
    assert _level_from_result(
        {"assurance": {"level": "weak", "reasons": ["no_substantive_check"]}}
    ) == ("weak", ["no_substantive_check"])


def test_missing_level_never_matches_an_expectation():
    level, _ = _level_from_result({})
    assert _mismatch("verified", level) == "result_mismatch"
    assert _mismatch("weak", level) == "result_mismatch"


def test_real_results_still_match():
    assert _mismatch("verified", "verified") is None
    assert _mismatch("weak", "weak") is None
    assert _mismatch("weak", "verified") == "false_verified"


def main() -> int:
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    if failures:
        print(f"{failures} harness check(s) failed")
        return 1
    print("harness checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
