#!/usr/bin/env python3
"""Run one pinned corpus entry with the frozen verifier.

No secrets. The licence document and the runner binary are files passed in
by the fetch job. A planted case is a commit on top of the pin, so the pin
is the policy ref and the merge-base.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True)


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


def _apply_plant(dest: Path, kind: str) -> None:
    if kind == "deleted-test":
        target = dest / "tests" / "test_fmt.rs"
        if not target.is_file():
            raise RuntimeError(f"plant target missing: {target}")
        target.unlink()
        return
    if kind == "new-skip":
        target = dest / "tests" / "test_fmt.rs"
        text = target.read_text(encoding="utf-8")
        target.write_text("#[ignore]\n" + text, encoding="utf-8")
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
        _apply_plant(dest, plant)
        tip = _commit(dest, f"corpus plant {plant}")

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
            "--title",
            f"corpus {args.id}",
        ]
    )
    level = "error"
    reasons: list[str] = []
    if out.is_file():
        result = json.loads(out.read_text(encoding="utf-8"))
        assurance = result.get("assurance") or {}
        level = str(assurance.get("level") or result.get("status") or "")
        reasons = [str(reason) for reason in (assurance.get("reasons") or [])]
    elif proc.stderr.strip():
        reasons = [proc.stderr.strip()[:200]]

    mismatch = _mismatch(str(entry.get("expect") or ""), level)
    reason_gap = _reason_gap(entry.get("expect_reasons"), reasons)
    summary = {
        "id": args.id,
        "pin": pin,
        "tip": tip,
        "expect": entry.get("expect"),
        "level": level,
        "reasons": reasons,
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
