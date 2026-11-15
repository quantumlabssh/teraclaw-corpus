#!/usr/bin/env python3
"""Self-checks for the corpus harness. No dependencies; run in CI.

    python corpus/test_run_entry.py

A result whose assurance level is missing must fail the entry, never count as a
pass or a skip. This is the regression that let a broken run look clean.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import license_ua_probe
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


def _run_ua_probe_with(responses):
    original = license_ua_probe._request
    queue = iter(responses)
    license_ua_probe._request = lambda *_args, **_kwargs: next(queue)
    try:
        with redirect_stdout(io.StringIO()):
            return license_ua_probe.main()
    finally:
        license_ua_probe._request = original


def test_verify_bic_403_is_not_a_pass():
    # A Cloudflare Browser Integrity Check block is also 403. The app refusal
    # must be distinguished by its JSON body and `license_ci_unavailable`.
    result = _run_ua_probe_with(
        [
            (401, "Unauthorized", "application/json", '{"error":"Unauthorized"}'),
            (403, "", "text/plain", "error code: 1010"),
            (403, "", "text/plain", "error code: 1010"),
        ]
    )
    assert result == 1


def test_verify_json_refusal_passes():
    result = _run_ua_probe_with(
        [
            (401, "Unauthorized", "application/json", '{"error":"Unauthorized"}'),
            (
                403,
                "license_ci_unavailable",
                "application/json",
                '{"error":"license_ci_unavailable"}',
            ),
            (403, "", "text/plain", "error code: 1010"),
        ]
    )
    assert result == 0


def test_repository_slug_names_the_target_not_the_corpus():
    from run_entry import repository_slug

    assert repository_slug("https://github.com/pallets/click.git") == "pallets/click"
    assert (
        repository_slug("https://github.com/sindresorhus/is-plain-obj.git")
        == "sindresorhus/is-plain-obj"
    )
    assert repository_slug("not a url") == ""


def test_rust_new_skip_plant_compiles_as_an_ignored_test():
    import tempfile
    from pathlib import Path

    from run_entry import _apply_plant

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "tests" / "test_fmt.rs"
        target.parent.mkdir(parents=True)
        target.write_text("use core::fmt;\n\n#[test]\nfn ok() {}\n", encoding="utf-8")

        _apply_plant(root, "new-skip", {})

        text = target.read_text(encoding="utf-8")
        assert text.startswith("use core::fmt;")
        assert "#[test]\n#[ignore]\nfn teraclaw_corpus_plant() {}" in text


def test_workflow_matrix_matches_the_manifest():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    workflow = (root / ".github" / "workflows" / "corpus.yml").read_text(
        encoding="utf-8"
    )
    block = workflow.split("matrix:", 1)[1].split("steps:", 1)[0]
    matrix = {
        line.strip()[2:]
        for line in block.splitlines()
        if line.strip().startswith("- ") and line.startswith("          - ")
    }
    expected = {entry["id"] for entry in manifest["entries"]}
    assert matrix == expected, (
        f"matrix/manifest drift: missing={sorted(expected - matrix)} "
        f"extra={sorted(matrix - expected)}"
    )


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
