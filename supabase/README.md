# Supabase workflow

This folder is the source of truth for database schema changes.

Read:

- [Data model reference](../docs/reference/data-model.md) for tables, RLS, and
  RPC ownership.
- [Development](../docs/05-development.md) for the local workflow.
- [Deployment and operations](../docs/06-deployment-and-operations.md) for
  staging and production.

## Migration rule

Applied migrations are immutable. Add a new timestamped forward migration to
change schema, data, RLS, grants, functions, or policies.

    supabase migration new <name>

## Local workflow

    supabase start
    supabase db reset
    supabase test db supabase/tests/database
    supabase db lint --local --fail-on warning

`db reset` rebuilds the local database from committed migrations. Never run a
reset against staging or production.

Generate a reviewed diff when useful:

    supabase db diff -f <name>

## macOS with Colima

    colima start --cpu 4 --memory 8 --disk 40 \
      --vm-type vz \
      --vz-rosetta \
      --mount-type virtiofs
    docker context use colima
    supabase start

Remove a stale `DOCKER_HOST` override when it points Supabase at the wrong
socket.

Stop cleanly:

    supabase stop
    colima stop

## Hosted environments

Normal staging and production migration deployment runs through GitHub Actions
from an exact release tag.

Direct remote commands are exceptional:

    supabase db pull
    supabase db push --dry-run
    supabase db push

Before using them:

1. confirm the linked project;
2. confirm the environment is not production unless the approved production
   procedure requires it;
3. preview the change;
4. preserve committed migration history; and
5. record the result.

Do not make routine schema changes in the Supabase Dashboard.

## Storage and Auth

- Create private Storage buckets through reviewed migrations.
- Object folders are implicit in object paths.
- `supabase/config.toml` controls local Auth.
- Hosted Auth providers, SMTP, callback URLs, and most Auth settings must be
  configured separately in each Supabase project.

Database backups do not automatically prove recovery of Storage objects.
