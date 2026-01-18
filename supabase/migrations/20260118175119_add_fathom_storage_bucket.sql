-- Create the private storage bucket used by Fathom.
-- Buckets are data (not schema), but we manage them via migrations for consistency.

insert into storage.buckets (id, name, public)
values ('fathom', 'fathom', false)
on conflict (id) do nothing;
