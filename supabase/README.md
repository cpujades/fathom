## Supabase workflow

This folder is the source of truth for database schema changes.

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
