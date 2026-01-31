-- Remove job update notifications used by legacy SSE endpoints.

DROP TRIGGER IF EXISTS job_update_trigger ON jobs;
DROP FUNCTION IF EXISTS notify_job_change();
