#!/usr/bin/env python3
"""Run one pinned corpus entry with the frozen verifier.

No secrets. The licence document and the runner binary are files passed in
by the fetch job. A planted case is a commit on top of the pin, so the pin
is the policy ref and the merge-base.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(
    argv: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=env, check=False, capture_output=True, text=True
    )


def _clone(url: str, sha: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    init = _run(["git", "init"], cwd=dest)
    if init.returncode != 0:
        raise RuntimeError(init.stderr.strip() or "git init failed")
    added = _run(["git", "remote", "add", "origin", url], cwd=dest)
    if added.returncode != 0:
        raise RuntimeError(added.stderr.strip() or "git remote add failed")
    fetched = _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=dest)
    if fetched.returncode != 0:
        raise RuntimeError(fetched.stderr.strip() or f"fetch failed for {sha}")
    checked = _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=dest)
    if checked.returncode != 0:
        raise RuntimeError(checked.stderr.strip() or "checkout failed")


def _commit(dest: Path, message: str) -> str:
    added = _run(["git", "add", "-A"], cwd=dest)
    if added.returncode != 0:
        raise RuntimeError(added.stderr.strip() or "git add failed")
    committed = _run(
        [
            "git",
            "-c",
            "user.email=corpus@teraclaw.local",
            "-c",
            "user.name=corpus",
            "commit",
            "-m",
            message,
        ],
        cwd=dest,
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip() or "git commit failed")
    sha = _run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
    if not sha:
        raise RuntimeError("plant commit has no sha")
    return sha


def _apply_plant(dest: Path, kind: str, entry: dict) -> None:
    if kind in {"deleted-test", "new-skip"}:
        relative = str(entry.get("plant_file") or "tests/test_fmt.rs")
        target = dest / relative
        if not target.is_file():
            raise RuntimeError(f"plant target missing: {target}")
        if kind == "deleted-test":
            target.unlink()
            return
        # Append, so the added lines carry the language's own skip marker. A
        # snippet is required for anything but Rust: the corpus may not assume
        # one language's syntax.
        snippet = entry.get("plant_snippet")
        if snippet:
            target.write_text(
                target.read_text(encoding="utf-8")
                + str(snippet).replace("\\n", "\n"),
                encoding="utf-8",
            )
        else:
            target.write_text(
                "#[ignore]\n" + target.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return
    if kind == "workflow":
        workflow = dest / ".github" / "workflows"
        workflow.mkdir(parents=True, exist_ok=True)
        (workflow / "plant.yml").write_text(
            "name: plant\non: workflow_dispatch\njobs: {}\n",
            encoding="utf-8",
        )
        return
    raise RuntimeError(f"unknown plant {kind}")


RUN_LEVELS = {"verified", "weak", "capped", "failed", "accepted"}


def _level_from_result(result: dict) -> tuple[str, list[str]]:
    """Read the assurance level, or fail the entry when it is absent.

    Reading the wrong shape is how an empty level once looked like a clean run;
    a result without a known level must never be treated as a pass.
    """
    assurance = result.get("assurance") or {}
    level = str(assurance.get("level") or result.get("status") or "").strip()
    reasons = [str(reason) for reason in (assurance.get("reasons") or [])]
    if level not in RUN_LEVELS:
        return "error", reasons + ["missing_level"]
    return level, reasons


def _mismatch(expect: str, level: str) -> str | None:
    expected = (expect or "").strip()
    actual = (level or "").strip()
    if actual == "verified" and expected != "verified":
        return "false_verified"
    if actual != expected:
        return "result_mismatch"
    return None


def _reason_gap(expected: list[str] | None, actual: list[str] | None) -> str | None:
    missing = [reason for reason in (expected or []) if reason not in (actual or [])]
    if not missing:
        return None
    return "missing_reason:" + ",".join(missing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    args = parser.parse_args()

    root = Path(args.root)
    manifest = json.loads((root / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["entries"] if item["id"] == args.id)
    dest = Path(args.work) / args.id
    out = Path(args.work) / f"{args.id}.json"
    policy = root / entry["policy"]
    pin = str(entry["sha"])
    _clone(str(entry["repo"]), pin, dest)
    plant = str(entry.get("plant") or "")
    tip = pin
    if plant:
        _apply_plant(dest, plant, entry)
        tip = _commit(dest, f"corpus plant {plant}")

    # The runner needs a writable data dir and an instance signing key, the same
    # way the reusable action sets them. Without a key the receipt is unsigned
    # and the run exits 2 before any check.
    data_dir = Path(args.work) / f"{args.id}.teraclaw-run"
    data_dir.mkdir(parents=True, exist_ok=True)
    run_env = {
        **os.environ,
        "TERACLAW_DATA_DIR": str(data_dir),
        "TERACLAW_INSTANCE_KEY_PATH": str(data_dir / "instance_key"),
    }

    proc = _run(
        [
            args.runner,
            "run",
            "--repo",
            str(dest),
            "--sha",
            tip,
            "--policy-ref",
            pin,
            "--policy-file",
            str(policy),
            "--license-file",
            args.license,
            "--repository",
            "quantumlabssh/teraclaw-corpus",
            "--repository-id",
            str(args.repository_id),
            "--scope",
            "verify",
            "--out",
            str(out),
            # Without --full the runner writes the DSSE receipt envelope, which
            # has no ``assurance``/``status`` keys, so the harness would read an
            # empty level even on a verified run.
            "--full",
            "--title",
            f"corpus {args.id}",
        ],
        env=run_env,
    )
    level = "error"
    reasons: list[str] = []
    if out.is_file():
        level, reasons = _level_from_result(
            json.loads(out.read_text(encoding="utf-8"))
        )
    else:
        # No receipt: keep whatever the runner said. Empty stderr plus a zero
        # output run is itself a finding, so name the exit code.
        detail = proc.stderr.strip() or proc.stdout.strip()
        reasons = [detail[-400:]] if detail else [f"runner exited {proc.returncode} with no output"]

    mismatch = _mismatch(str(entry.get("expect") or ""), level)
    reason_gap = _reason_gap(entry.get("expect_reasons"), reasons)
    summary = {
        "id": args.id,
        "pin": pin,
        "tip": tip,
        "expect": entry.get("expect"),
        "level": level,
        "reasons": reasons,
        "exit_code": proc.returncode,
        "mismatch": mismatch,
        "reason_gap": reason_gap,
    }
    Path(args.work, f"{args.id}.summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary))
    if mismatch or reason_gap:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
