# Storage access boundary

Talven keeps both Supabase Storage buckets private and mediates every storage
operation through the backend:

- `fathom_groq`: the worker uploads temporary audio with the service client,
  creates a short-lived URL for Groq, and deletes the object after use.
- `fathom`: the API first reads the requested summary with the user's
  authenticated client (and therefore summary RLS), then uses the service
  client to upload a PDF or issue a short-lived signed URL.

The browser does not list, read, upload, update, or delete Storage objects
directly. Authenticated access to `storage.objects` is therefore intentionally
absent; ownership is checked against application tables before the backend
performs a storage operation.

`supabase/tests/database/storage_access.test.sql` proves that both buckets are
private, no Talven policy grants direct authenticated object access, RLS is
enabled, and authenticated roles cannot list either bucket.
