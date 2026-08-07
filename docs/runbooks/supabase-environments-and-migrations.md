# Supabase environments and migrations

This page connects Talven's local setup, pull-request checks, staging project,
and future production project. They use the same committed migrations, but they
are four separate databases. A command run against one does not change another.

## The four database contexts

| Context | Database | Purpose | Uses hosted credentials? |
| --- | --- | --- | --- |
| Local development | Supabase containers on the developer's machine | Run Auth, Postgres, Storage, and the application locally | No |
| Pull-request CI | Temporary Postgres on a GitHub runner | Prove every migration, database test, and lint rule from a clean start | No |
| Staging | A dedicated hosted Supabase project | Rehearse the exact released code with non-production data | Yes, staging only |
| Production | A separate hosted Supabase project | Store real user and billing data | Yes, production only |

For example, a local job with `id = 11111111-1111-1111-1111-111111111111`
exists only in the local database. A staging job may coincidentally have a
similar UUID, but it is a different row in a different database. CI starts
empty, creates its own test rows, and discards them when the job ends.

## What is shared and what stays separate

| Item | Source of truth | Where it applies |
| --- | --- | --- |
| Tables, functions, RLS policies, grants, and buckets | `supabase/migrations/*.sql` | Local, CI, staging, and production |
| Database tests | `supabase/tests/database/*.sql` | Local verification and PR CI |
| Development seed rows | `supabase/seed.sql` | Local reset; not production deployment |
| Local ports and local Auth behavior | `supabase/config.toml` | Local Supabase only |
| Hosted Auth URLs, email, SMTP, CAPTCHA, and provider settings | Each hosted project's Dashboard | Configure separately in staging and production |
| Application data and Storage objects | The database or bucket in that environment | Never copied automatically between environments |

A migration describes a database change. It does not copy local users, jobs,
briefings, or files into staging or production. It also does not copy the local
Auth settings from `config.toml` into a hosted Dashboard.

## Local development

Supabase CLI uses a Docker-compatible runtime. On macOS, start Docker Desktop
or the documented Colima setup, then run:

```bash
supabase start
supabase db reset
supabase test db supabase/tests/database
supabase db lint --local --fail-on warning
```

- `supabase start` starts the local Supabase services.
- `supabase db reset` rebuilds the local database from all committed migrations
  and then applies the local seed.
- `supabase test db` runs the pgTAP database tests.
- `supabase db lint --local` examines the resulting local schema.

`db reset` is intentionally destructive to the local database. It is safe only
when the local data is disposable. Stop the stack with `supabase stop`.

To add a schema change:

```bash
supabase migration new <short_name>
```

Edit the new SQL file and rebuild locally from a clean database. Once a
migration has reached a shared environment, do not edit it; add a later
migration that makes the next change.

## What the pull-request check does

When a PR changes `supabase/**`, `.github/workflows/supabase-pr.yml` performs
these steps in order:

1. Start a local database inside the temporary GitHub runner.
2. Apply every migration in timestamp order with
   `supabase migration up --local`.
3. Run `supabase test db supabase/tests/database`.
4. Run `supabase db lint --local --fail-on warning`.
5. Discard the runner and its database after the job.

The workflow does not read `SUPABASE_URL`, link a project, or contact staging
or production. A migration failure therefore means “this SQL could not build a
clean database,” not “the hosted Supabase project is broken.” Later steps do
not run after an earlier failure. For example, if migration parsing fails, a
green database test or lint result does not yet exist for that run.

This gate proves the committed schema, RLS/RPC rules, and pgTAP cases can work
together from an empty database. It does not prove hosted Auth settings, real
email delivery, hosted Storage HTTP behavior, backups, or the application
journey against a real staging project.

## How staging receives migrations

After a successful release on `main`, the release workflow passes its exact
generated tag to `.github/workflows/staging.yml`. Staging compares that tag
with the preceding release and checks whether `supabase/**` changed. If it did,
the workflow:

1. Checks out the exact released tag.
2. Uses the `staging` GitHub environment's `SUPABASE_ACCESS_TOKEN`,
   `SUPABASE_PROJECT_REF`, and `SUPABASE_DB_PASSWORD`.
3. Links the CLI to the staging project.
4. Previews pending changes with `supabase db push --dry-run`.
5. Applies the pending migrations with `supabase db push`.

The staging workflow can also be started manually by supplying an exact release
tag. It never targets production when its GitHub environment secrets correctly
belong to the staging project.

## How production receives migrations

Production is deliberately separate. An operator manually runs
`.github/workflows/promote.yml` and supplies an exact release tag such as
`v0.20.5`. The workflow checks out that tag, uses the `prod` GitHub environment
secrets, links the production project, previews the migration push, and then
applies it.

Normal staging and production releases should use those workflows. Do not make
an untracked Dashboard/SQL Editor change or manually run `db push` as a shortcut.
If a hosted project was intentionally changed outside migrations, use `db pull`
only as a recovery/reconciliation operation and review the generated SQL.

Before any linked CLI command, confirm the project reference. Never run a
linked reset against production. Local commands should say `--local` where the
CLI supports it; remote deployment commands belong in the controlled workflows.

## Why Talven has two Supabase connections

Talven reaches the same project in two different ways:

```text
Supabase HTTP path:
https://abc.supabase.co + a publishable or backend secret key

Persistent Postgres path:
postgresql://postgres:<password>@db.abc.supabase.co:5432/postgres
```

The HTTP path handles Auth, table APIs, and Storage. The worker also keeps a
Postgres session open for `LISTEN/NOTIFY`, so it can wake when a job arrives.
That listener needs a connection that preserves one database session. Use the
direct connection when the deployment host supports it, or Supavisor's session
mode when an IPv4-compatible pooler is required. Do not use transaction mode
for the listener: transaction pooling does not preserve the session that owns
`LISTEN`.

The deployment host and exact connection endpoint are future hosting choices.
The requirement for a persistent session is already part of Talven's worker
architecture. Hosted runtime connections also use TLS.

## Backups are two separate controls

A Supabase database backup protects Postgres rows and Storage metadata. It does
not restore the file objects themselves. Before public use, enable and rehearse
both database recovery and a separate Storage-object backup/recovery process.

## Official Supabase references

- [CLI local development](https://supabase.com/docs/guides/local-development/cli/getting-started)
- [Local development workflow and local versus linked commands](https://supabase.com/docs/guides/local-development/cli-workflows)
- [Database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [Testing a database with pgTAP](https://supabase.com/docs/guides/database/testing)
- [Managing local, staging, and production environments](https://supabase.com/docs/guides/deployment/managing-environments)
- [Direct and pooled Postgres connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Database backup scope, including the Storage-object limitation](https://supabase.com/docs/guides/platform/backups)
- [Auth redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)

For Talven's tables and access rules, continue with
[Database, RLS, and persistence](../architecture/database-and-persistence.md).
For every variable, see [Environment configuration](../reference/environment.md).
