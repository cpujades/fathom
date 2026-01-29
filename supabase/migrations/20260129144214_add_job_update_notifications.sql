-- Add Postgres NOTIFY trigger for job updates to enable real-time updates without polling

-- Create notification function that fires on job updates
CREATE OR REPLACE FUNCTION notify_job_change()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  -- Send notification with job_id as the payload
  PERFORM pg_notify(
    'job_updates',
    json_build_object(
      'id', NEW.id,
      'status', NEW.status,
      'stage', NEW.stage,
      'progress', NEW.progress
    )::text
  );
  RETURN NEW;
END;
$$;

-- Create trigger that fires after each UPDATE on jobs table
CREATE TRIGGER job_update_trigger
AFTER UPDATE ON jobs
FOR EACH ROW
WHEN (
  -- Only notify if relevant fields changed to reduce noise
  OLD.status IS DISTINCT FROM NEW.status OR
  OLD.stage IS DISTINCT FROM NEW.stage OR
  OLD.progress IS DISTINCT FROM NEW.progress OR
  OLD.summary_id IS DISTINCT FROM NEW.summary_id OR
  OLD.error_code IS DISTINCT FROM NEW.error_code
)
EXECUTE FUNCTION notify_job_change();

-- Add comment for documentation
COMMENT ON FUNCTION notify_job_change() IS 'Sends a notification on the job_updates channel when a job is updated';
COMMENT ON TRIGGER job_update_trigger ON jobs IS 'Triggers real-time notifications when job status changes';
