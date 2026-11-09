#!/usr/bin/env python3
"""Weekly licence refusal probe.

The refresh endpoint must not reveal whether a licence/install pair exists.
Send the same wrong signature once for a dedicated test-account pair and once
for unknown ids; both must return 403 `license_request_sig_invalid`.

Use a separate teraclaw.org test account with its own internal grant and one
activation. Never use the owner's licence or token. Ids and token are
repository secrets; this script prints only status/error codes.

Configuration:
  TERACLAW_PROBE_READ_TOKEN    read-only key for the test account
  TERACLAW_PROBE_LICENSE_ID    licence_id from the test account
  TERACLAW_PROBE_INSTALL_ID    matching install_id
  TERACLAW_PROBE_CONFIGURED    repository variable, "true" once the secrets exist

Before configuration this prints a GitHub warning and exits 0. Once
TERACLAW_PROBE_CONFIGURED is true, a missing secret is a hard failure.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://teraclaw.org"
# Keep in sync with teraclaw_engine.licensing.user_agents.ENGINE_USER_AGENT.
USER_AGENT = "TeraClaw-Engine/0.9.10 (+https://teraclaw.org)"
WRONG_SIG = f"ed25519:{'00' * 64}"


def _post(body: dict, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE}/api/license/refresh",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
            "authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    except urllib.error.URLError as error:
        print(f"::error::network error: {error.reason}")
        return 0, {}
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}


def _body(license_id: str, install_id: str) -> dict:
    return {
        "license_id": license_id,
        "install_id": install_id,
        "nonce": secrets.token_hex(16),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request_sig": WRONG_SIG,
    }


def main() -> int:
    token = os.environ.get("TERACLAW_PROBE_READ_TOKEN", "").strip()
    license_id = os.environ.get("TERACLAW_PROBE_LICENSE_ID", "").strip()
    install_id = os.environ.get("TERACLAW_PROBE_INSTALL_ID", "").strip()
    configured = os.environ.get("TERACLAW_PROBE_CONFIGURED", "").strip().lower() == "true"

    if not token or not license_id or not install_id:
        if configured:
            print(
                "::error::license probe is configured but TERACLAW_PROBE_READ_TOKEN, "
                "TERACLAW_PROBE_LICENSE_ID, or TERACLAW_PROBE_INSTALL_ID is missing"
            )
            return 1
        print("::warning::license probe not configured")
        return 0

    known_status, known = _post(_body(license_id, install_id), token)
    unknown_status, unknown = _post(_body("lic_probe_missing", "install_probe_missing"), token)
    print(f"known pair: status={known_status} error={known.get('error', '-')}")
    print(f"unknown ids: status={unknown_status} error={unknown.get('error', '-')}")
    expected = (403, "license_request_sig_invalid")
    if (known_status, known.get("error")) == expected and (
        unknown_status,
        unknown.get("error"),
    ) == expected:
        print("OK")
        return 0
    print("::error::license refusal is not uniform (possible id-existence leak)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
