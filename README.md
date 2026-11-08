# TeraClaw proof corpus

Public hosted proof corpus. It does not run on a self-hosted runner. It does
not call `teraclaw-verify-action`. That action verifies the repository that
calls it. This corpus verifies pinned third-party commits instead.

Triggers are `schedule` and `workflow_dispatch` only. A pull request cannot
start it.

`permissions` is `contents: read`. The corpus does not post GitHub checks. A
false `verified` fails the job. Weekly evidence is the entry summary artifact.

## Two jobs

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
