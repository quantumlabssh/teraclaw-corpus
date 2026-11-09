# TeraClaw proof corpus

Public hosted proof corpus. It does not run on a self-hosted runner. It does
not call `teraclaw-verify-action`. That action verifies the repository that
calls it. This corpus verifies pinned third-party commits instead.

Triggers are `schedule` and `workflow_dispatch` only. A pull request cannot
start it.

`permissions` is `contents: read`. The corpus does not post GitHub checks. A
false `verified` fails the job. Weekly evidence is the entry summary artifact.

## Three jobs

`license-probe` runs only this repository's `corpus/license_refusal_probe.py`
and a separate teraclaw.org test-account token. It sends a wrong refresh
signature for the test licence/install pair and for unknown ids; both must
return `403 license_request_sig_invalid`. It never checks out or runs a target
repo. Before configuration it prints `::warning::license probe not configured`;
once `TERACLAW_PROBE_CONFIGURED=true` is set, a missing secret fails the job.

The same job first runs `corpus/license_ua_probe.py`. The engine and verify
User-Agents must get JSON, and default `Python-urllib` is the Browser Integrity
Check baseline: teraclaw.org answers `403 text/plain` with `error code: 1010`.
A challenge for the engine or verify client fails the job; if Python-urllib
stops being blocked, the job warns so a Cloudflare setting change is visible.
The harness check includes a regression test that a 403 `error code: 1010`
block is not mistaken for the verify client's JSON `license_ci_unavailable`
refusal, even though both use status 403.

`fetch` holds `TERACLAW_LICENSE_CI_KEY` and runs no target code. It exchanges
the key for a CI licence bound to repository `1449567302`, downloads the
runner, and checks the SHA-256 and Sigstore bundle. It passes the runner
binary and the licence document on as an artifact. The key is not in that
artifact.

`entries` is a matrix with no secrets. For each row in `corpus/manifest.json`
it clones the pinned SHA, applies a planted case as a commit on top of that
pin, and runs:

```text
teraclaw-verify run --repo <clone> --sha <tip> --policy-ref <pin> --policy-file <corpus policy>
```

The pin is the policy ref and the merge-base. The corpus policy file is this
repo's file, not the target's. The job fails on a false `verified` or any
other mismatch.

The runner hash variable stays empty until a signed runner exists. While it
is empty, `fetch` and `entries` do not run.

## Probe secrets and variable

Create a separate teraclaw.org test account with its own internal grant and one
activation. Mint a read-only key there. Do **not** use the owner's licence.

| Name | Kind | Value |
| --- | --- | --- |
| `TERACLAW_PROBE_READ_TOKEN` | secret | read-only test-account key |
| `TERACLAW_PROBE_LICENSE_ID` | secret | test-account `license_id` |
| `TERACLAW_PROBE_INSTALL_ID` | secret | matching `install_id` |
| `TERACLAW_PROBE_CONFIGURED` | variable | `true` once the three secrets exist |

While `TERACLAW_PROBE_CONFIGURED` is unset or not `true`, the job prints
`::warning::license probe not configured` and passes. Once it is `true`, a
missing secret fails the job. The probe prints only status/error codes.

`ENGINE_VERSION` in the probe must match the engine's `_version.py`. The engine
repo's `scripts/sync-version.mjs` fails when a sibling `../teraclaw-corpus`
checkout is present and the marker is stale, so `pnpm sync-version` catches the
drift before a release.

## Repository variables

Set these after the signed runner is uploaded. `fetch` fails if any of the
last four is empty.

| Variable | Value |
| --- | --- |
| `TERACLAW_RUNNER_SHA256` | SHA-256 of the signed archive. Empty keeps the corpus dormant. |
| `TERACLAW_RUNNER_DOWNLOAD_HOST` | `0c3b1eaf3761b5f9aee5c81675890a3f.r2.cloudflarestorage.com`. This is the release account (`R2_ACCOUNT_ID`), not the images account. |
| `TERACLAW_RUNNER_SOURCE_COMMIT` | `github.sha` of the run that built the runner. |
| `TERACLAW_RUNNER_SIGNER_WORKFLOW` | Workflow ref in the certificate: `quantumlabssh/teraclaw/.github/workflows/release-verify-runner.yml@<ref>`, or the absolute `https://github.com/...` form. |
| `TERACLAW_SOURCE_REPOSITORY_ID` | `1156873560`. |

The website needs `R2_VERIFY_READ_*` and `R2_VERIFY_ACCOUNT_ID` for the private
`teraclaw-verify` bucket; without them the licence exchange returns no runner
URL. `R2_VERIFY_ACCOUNT_ID` must be the account that owns the bucket, which is
the release account used by the upload workflow, not the images account.
