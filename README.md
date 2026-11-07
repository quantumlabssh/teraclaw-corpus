# TeraClaw proof corpus

Public hosted proof corpus. It does not run on a self-hosted runner. The only
secret is `TERACLAW_LICENSE_CI_KEY`. Do not add any other secret.

The workflow calls `quantumlabssh/teraclaw-verify-action` at the `hardening`
commit `c91472d1ae06a66f0eab2d4b4570f7e6cf851b75`. That call is the customer
path: it verifies this repository. It does not clone the pinned third-party
entries. Those entries and their planted cases live in `corpus/manifest.json`
and `corpus/policies/`. They run once a signed runner hash is pinned.

`permissions` is `contents: read` only. The called action also asks to post a
check. GitHub intersects the caller token with that request, so the check post
cannot succeed until this workflow grants `checks: write`. That grant is not
set here.

The runner hash, download host, and signer pin are repository variables. They
stay empty until a signed runner exists. The action is not called while the
hash variable is empty.

Mint `license:ci` for this repository's numeric id, then store it as
`TERACLAW_LICENSE_CI_KEY`.
