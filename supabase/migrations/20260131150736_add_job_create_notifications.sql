-- Notify workers when new jobs are inserted.

CREATE OR REPLACE FUNCTION notify_job_created()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  PERFORM pg_notify(
    'job_created',
    json_build_object(
      'id', NEW.id,
      'created_at', NEW.created_at
    )::text
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS job_insert_trigger ON jobs;
CREATE TRIGGER job_insert_trigger
AFTER INSERT ON jobs
FOR EACH ROW
EXECUTE FUNCTION notify_job_created();

COMMENT ON FUNCTION notify_job_created() IS 'Sends a notification on job_created when a job is inserted';
COMMENT ON TRIGGER job_insert_trigger ON jobs IS 'Triggers notifications for newly inserted jobs';
