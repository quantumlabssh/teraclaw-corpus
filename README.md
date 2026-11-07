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
