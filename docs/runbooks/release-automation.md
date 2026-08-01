# Release automation

Talven creates a release after a pull request is merged into `main`. The
workflow calculates a semantic version from conventional commits, updates the
changelog and Python version, pushes one release commit and tag, and publishes
the GitHub release.

## Why two tokens are used

The workflow uses GitHub's short-lived `github.token` for checkout and GitHub
API reads. GitHub creates it for the job and expires it automatically.

The repository's active `main` ruleset requires a pull request and status
checks. Its bypass is granted to the repository administrator role, not to the
GitHub Actions app. The built-in token therefore cannot be relied on to push
the generated release commit directly to `main`.

`RELEASE_AUTOMATION_TOKEN` is a repository secret containing a token for an
administrator account that may bypass that ruleset. It is used only for the
final release commit and tag push.

## Required token properties

Use a fine-grained personal access token where possible:

- resource owner: the account that owns or administers this repository;
- repository access: only `cpujades/fathom`;
- repository permission: **Contents — Read and write**;
- shortest practical expiry with a calendar reminder; and
- no unrelated organization or account permissions.

The account behind the token must retain the administrator/bypass role. Write
permission without ruleset bypass is not sufficient for this direct-main
release design.

## Create or rotate the secret

1. In GitHub account settings, create or regenerate the fine-grained token.
2. Copy it once; do not put it in `.env`, source code, an issue, or a log.
3. Open this repository's **Settings > Secrets and variables > Actions**.
4. Replace the repository secret named `RELEASE_AUTOMATION_TOKEN`.
5. Re-run the failed release workflow or merge the next conventional product
   change into `main`.
6. Confirm that checkout, credential verification, release commit/tag push,
   and GitHub release publication all succeed.

Rotating the secret does not require a code deployment. Re-running an old
workflow uses the workflow file stored in its original commit; a refreshed
valid token fixes its authentication, but it does not include newer workflow
diagnostics.

## Failure meanings

| Failing step or message | Meaning | Action |
| --- | --- | --- |
| `Verify release push credentials`: invalid, expired, or inaccessible | Secret exists but GitHub rejected it | Rotate the token and replace the secret |
| `does not have repository contents write access` | Token is valid but read-only | Add Contents read/write permission |
| Push rejected by repository rules | Token's account cannot bypass `main` rules | Use the administrator account or redesign releases to go through a PR |
| No conventional commits detected | Merged commits do not match the release contract | Fix commit/merge-message policy; do not rotate credentials |
| GitHub release publication fails after a successful tag push | Release API problem or permission issue | Inspect that step; do not create a duplicate tag manually |

The workflow deliberately checks out with `github.token` first. An expired
release secret therefore produces one clear credential-verification failure
instead of making a read-only checkout look like a repository outage.

## Security and second-order effects

This token can bypass the normal `main` pull-request path, so compromise has a
higher impact than an ordinary read token. Keep its repository scope minimal,
rotate it, restrict who can edit Actions secrets/workflows, and review every
workflow change affecting the release job.

A longer-term alternative is a narrowly scoped GitHub App or a release-PR
design. Either changes workflow identity, check-trigger behavior, and merge
semantics and should be designed separately rather than mixed into a token
rotation.
