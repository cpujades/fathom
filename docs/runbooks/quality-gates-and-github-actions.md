# Quality gates and GitHub Actions

This page explains what Talven checks locally, on every pull request, after a
merge, and during database promotion. The workflow files remain the executable
source of truth; this is the owner-readable map.

## The short version

```text
While editing
  -> targeted tests and pre-commit

Before requesting review
  -> full backend, frontend, API-contract, and relevant database checks

Pull request
  -> shared GitHub checks on a clean runner

Merge to main
  -> version, changelog, tag, and GitHub release
  -> changed Supabase migrations go to staging

Production promotion
  -> operator selects an exact release tag
  -> that tag's Supabase migrations go to production
```

There is no application-hosting workflow yet. The staging and production
workflows currently deploy Supabase migrations only. Web, API, and worker
deployment will be added after a hosting platform is selected.

## Local pre-commit checks

Install the repository hook once per clone:

```bash
uv run pre-commit install
```

It then runs automatically when creating a commit. To check the complete
repository deliberately:

```bash
uv run --locked pre-commit run --all-files
```

The configuration in `.pre-commit-config.yaml` checks:

- Python syntax;
- accidentally added large files, merge markers, invalid JSON/TOML/YAML,
  debugger statements, and private-key patterns;
- end-of-file and trailing-whitespace formatting;
- commits made directly on `main`;
- Ruff linting and formatting for Python; and
- strict `ty` type checking when backend Python files are involved.

The hook is intentionally a fast first line of defense. Passing it does not run
the complete backend test suite, a database stack, or a real provider.

## Full local checks

Run the same main code-quality commands used by PR CI:

```bash
# Backend
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run ty check apps/backend/fathom
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest discover -s apps/backend/tests

# Frontend
pnpm --filter @fathom/web lint
pnpm --filter @fathom/web typecheck
pnpm --filter @fathom/web test
pnpm --filter @fathom/web build

# Generated API contract
pnpm check:api-contract
```

For a changed database, also run against disposable local Supabase:

```bash
supabase db reset
supabase test db supabase/tests/database
supabase db lint --local --fail-on warning
```

`supabase db reset` deletes local database data. Never run a reset against a
shared or production project. The complete database environment explanation is
in [Supabase environments and migrations](./supabase-environments-and-migrations.md).

## Pull-request workflows

| Workflow | When it runs | What it proves |
| --- | --- | --- |
| `.github/workflows/checks.yml` | Every PR | Locked dependency installation; backend lint, format, types, pre-commit, OpenAPI drift, and tests; frontend lint, application/API-client types, generated-client drift, unit tests, and production build |
| `.github/workflows/commit-messages.yml` | PR opened, updated, reopened, edited, or marked ready | At least one non-merge commit uses the accepted Conventional Commit format, so the release can classify the change |
| `.github/workflows/security.yml` | Every PR | Dependency Review plus CodeQL analysis for Python, JavaScript/TypeScript, and Actions workflow code |
| `.github/workflows/supabase-pr.yml` | Every PR, doing database work only when `supabase/**` or its workflow changed | A temporary local database can apply every migration, pass all pgTAP suites, and pass schema lint |

PR CI runs on a clean GitHub runner, so it catches missing files or undeclared
dependencies that may be hidden on a developer's machine. It reruns the
CI-suitable pre-commit hooks but skips `no-commit-to-branch`, because CI checks
the PR commit rather than creating a local commit.

The commit-message workflow does not require every commit to be conventional.
It requires at least one qualifying non-merge commit, and only qualifying
commits are eligible for generated release notes. Keeping every intentional
commit conventional is still the project convention.

## What happens after merge

| Workflow | Trigger | Current effect |
| --- | --- | --- |
| `.github/workflows/release.yml` | Push to `main` | Reads the merged PR commits, calculates the next semantic version, updates `CHANGELOG.md`, `pyproject.toml`, and `uv.lock`, creates the release commit and tag, and publishes the GitHub release |
| `.github/workflows/staging.yml` | Successful release workflow, or manual dispatch | If Supabase changed, links the staging project, previews `db push`, and applies pending migrations using the `staging` GitHub environment secrets |
| `.github/workflows/promote.yml` | Manual dispatch with an exact release tag | Resolves that immutable tag, summarizes it, links the production project, previews `db push`, and applies that tag's migrations using the `prod` GitHub environment secrets |

The security workflow also runs CodeQL after pushes to `main` and on its weekly
schedule. Dependency Review is PR-only because it compares proposed dependency
changes with the base branch.

The release workflow's credentials and protected-branch behavior are explained
in [Release automation](./release-automation.md). Staging and production
database credentials belong to separate GitHub environments; they are not read
by the PR database workflow.

## Test layers that are intentionally separate

| Layer | Automatic in normal PR CI? | Why it exists |
| --- | --- | --- |
| Ordinary backend/frontend tests | Yes | Fast deterministic behavior and regression coverage |
| Supabase pgTAP suites | Yes, when Supabase files changed | Clean-schema, RLS, RPC, billing, concurrency, and storage rules |
| Gate A fake recovery rehearsal | Covered by ordinary backend discovery; runnable directly | Focused, deterministic recovery and concurrency diagnosis |
| Gate B Python database integrations | No; they skip without an explicit disposable database URL | Additional live-Postgres concurrency proof without risking shared data |
| Gate C authenticated product rehearsal | No; explicit opt-in | Full local Auth/API/worker/SSE/PDF journey with fake providers |
| Polar catalog sync | No live sync; frontend tests read the public plan contract and ordinary checks cover script syntax/lint | `--dry-run` validates locally; sandbox/production synchronization is an explicit provider operation with environment credentials |
| Real Groq/OpenRouter/Polar exercises | No | Provider behavior, quality, latency, cost, and webhook delivery |
| Human UX/accessibility review | No | Comprehension, visual quality, assistive technology, and real-device behavior |

Exact Gate A/B/C setup and acceptance criteria are in
[Local load and recovery rehearsal](./local-recovery-rehearsal.md). Real
provider and human evidence remain release-candidate work; a green PR cannot
manufacture that evidence.

## How to read a failure

Start with the first failing step, because later steps may never have run.

Examples:

- migration application failed: the database tests and lint below it have not
  yet proved anything;
- OpenAPI contract failed: regenerate and review the client/spec change rather
  than editing the generated file blindly;
- frontend build failed but tests passed: runtime logic may be sound while the
  deployable production bundle is not;
- Dependency Review failed: inspect the dependency change and advisory rather
  than treating it as a general test failure; and
- release push failed: inspect the release-token/ruleset diagnosis; do not
  create a competing tag manually.

After a fix, confirm that the replacement run reaches and passes every step
that the original failure prevented.
