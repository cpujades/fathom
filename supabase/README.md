## Supabase workflow

This folder is the source of truth for database schema changes.

### Migration guidelines
- Migrations are immutable once pushed. If a change is needed later, create a new migration that updates the schema or policies.
  - Why: editing applied migrations makes envs drift and breaks reproducibility.

### Prerequisites
- Install the Supabase CLI.
- Link the project once before using remote commands.

Docs: https://supabase.com/docs/reference/cli/introduction

### Create a migration
```bash
supabase migration new <name>
```

### Apply migrations locally
```bash
supabase start
supabase db reset
```

### Local development with Colima (macOS)
```bash
colima start --cpu 4 --memory 8 --disk 40 --vm-type vz --vz-rosetta --mount-type virtiofs
docker context use colima
supabase start
```
Notes:
- Ensure `DOCKER_HOST` is not set in your shell config. It overrides the Docker context.
  - Why: Supabase uses Docker, and a stale `DOCKER_HOST` forces it to the wrong socket.
- Increase the Colima disk if image extraction fails with "no space left on device".

### Stop local Supabase cleanly
```bash
supabase stop
colima stop
```
Why: this stops containers first, then shuts down the VM to avoid orphaned Docker state.

### Diff and generate a migration
Compare a target database against the shadow database built from local migrations.
```bash
supabase db diff -f <name>
```

### Pull schema from a linked project
```bash
supabase db pull
```

### Push migrations to a linked project
```bash
supabase db push
```

### Storage buckets, folders, and auth config
- Buckets: recommended to manage via SQL migrations for consistency across environments.
  - Example:
    ```sql
    insert into storage.buckets (id, name, public)
    values ('fathom', 'fathom', false)
    on conflict (id) do nothing;
    ```
  - Why: buckets are data, not schema, but you still want them to exist everywhere.
- Folders: no need to pre-create; they are implicit in object paths (e.g. `user_id/file.pdf`).
- Auth providers/settings:
  - Local: `supabase/config.toml` controls local auth behavior.
  - Staging/Prod: configure providers and email/SMS settings in the Supabase dashboard.
  - Why: most auth settings are not expressed as SQL migrations.

### Troubleshooting
- "Cannot connect to the Docker daemon": ensure `docker context use colima` and remove any `DOCKER_HOST` overrides from shell config.
- "no space left on device": increase Colima disk size or prune Docker images/volumes.
- "address already in use": update ports in `supabase/config.toml`.
- Storage policy role errors: run storage changes as a role that can `set role supabase_storage_admin` (prod uses `postgres`).
