#!/usr/bin/env python3
"""Weekly User-Agent probe for the licensed API paths.

Cloudflare's Browser Integrity Check is on for teraclaw.org. It answers
`403 text/plain` with `error code: 1010` for default Python-urllib agents,
while the engine and verify clients pass. Keep that baseline visible: the
engine and verify checks fail on a challenge, and the Python-urllib check
warns if Browser Integrity Check stops blocking it.

The engine and verify User-Agents must match the engine's `_version.py`. The
engine repo's `scripts/sync-version.mjs` checks `ENGINE_VERSION` in
`license_refusal_probe.py`; this probe reuses it so there is one marker.

Configuration: none. The requests are unauthenticated and print only status,
error code, and content type.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from license_refusal_probe import ENGINE_VERSION

BASE = "https://teraclaw.org"
ENGINE_UA = f"TeraClaw-Engine/{ENGINE_VERSION} (+https://teraclaw.org)"
VERIFY_UA = f"teraclaw-verify/{ENGINE_VERSION}"
PYTHON_UA = f"Python-urllib/{sys.version_info.major}.{sys.version_info.minor}"


def _request(
    method: str,
    path: str,
    user_agent: str,
    body: bytes | None = None,
    accept: str | None = "application/json",
) -> tuple[int, str, str, str]:
    headers = {"user-agent": user_agent}
    if accept:
        headers["accept"] = accept
    if body is not None:
        headers["content-type"] = "application/json"
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    last_error = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                raw = response.read()
                content_type = response.headers.get_content_type()
            break
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read()
            content_type = error.headers.get_content_type()
            break
        except urllib.error.URLError as error:
            last_error = f"network error: {error.reason}"
            if attempt == 0:
                time.sleep(2)
    else:
        return 0, "", "", last_error

    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {}
    code = ""
    if isinstance(payload, dict):
        code = str(payload.get("error") or payload.get("code") or "")
    return status, code, content_type, text


def main() -> int:
    failures: list[str] = []

    for label, user_agent, path, expected_status, expected_code in (
        ("engine", ENGINE_UA, "/api/license/refresh", 401, "Unauthorized"),
        ("verify", VERIFY_UA, "/api/license/ci", 403, "license_ci_unavailable"),
    ):
        status, code, content_type, raw = _request("POST", path, user_agent, b"{}")
        ok = (
            status == expected_status
            and code == expected_code
            and "json" in content_type
            and "error code: 1010" not in raw
        )
        print(
            f"{label} ua={user_agent.split('/')[0]} path={path} "
            f"status={status} error={code or '-'} content_type={content_type or '-'} "
            f"{'OK' if ok else 'BLOCKED_OR_CHANGED'}"
        )
        if not ok:
            failures.append(label)

    # Browser Integrity Check baseline: default Python-urllib gets 1010.
    status, _code, content_type, text = _request(
        "GET",
        "/api/license/key",
        PYTHON_UA,
        accept=None,
    )
    if status == 403 and "error code: 1010" in text:
        print(
            f"python-urllib ua={PYTHON_UA} path=/api/license/key "
            f"status=403 content_type={content_type or '-'} BIC_BLOCK_EXPECTED"
        )
    elif status == 200 and "json" in content_type:
        print(
            f"python-urllib ua={PYTHON_UA} path=/api/license/key "
            f"status=200 content_type={content_type or '-'} BIC_NOT_BLOCKING"
        )
        print(
            "::warning::Browser Integrity Check no longer blocks Python-urllib; "
            "confirm the Cloudflare setting is intended."
        )
    else:
        failures.append("python-urllib")
        print(
            f"python-urllib ua={PYTHON_UA} path=/api/license/key "
            f"status={status} content_type={content_type or '-'} UNEXPECTED"
        )

    if failures:
        print("FAILED", ",".join(failures))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
