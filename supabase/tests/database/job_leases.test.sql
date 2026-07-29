begin;

set local search_path = extensions, public, pg_catalog;

select plan(14);

select ok(
  not has_function_privilege('authenticated', 'public.renew_job_lease(uuid,uuid,interval)', 'execute'),
  'authenticated users cannot renew worker leases'
);
select ok(
  has_function_privilege('service_role', 'public.renew_job_lease(uuid,uuid,interval)', 'execute'),
  'service role can renew worker leases'
);

insert into public.jobs (id, user_id, status, url, stage, progress)
values (
  '10000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001',
  'queued',
  'https://www.youtube.com/watch?v=lease-test',
  'queued',
  5
);

create temporary table claimed_job as
select *
from public.claim_next_job(interval '2 minutes');

select is(
  (select id from claimed_job),
  '10000000-0000-0000-0000-000000000001'::uuid,
  'claim returns the queued job'
);
select is((select status from claimed_job), 'running', 'claim marks the job running');
select ok((select lease_token is not null from claimed_job), 'claim issues a lease token');
select ok((select heartbeat_at is not null from claimed_job), 'claim records a heartbeat');
select ok(
  (select lease_expires_at > heartbeat_at from claimed_job),
  'claim sets a future lease expiry'
);

select ok(
  public.renew_job_lease(
    '10000000-0000-0000-0000-000000000001',
    (select lease_token from claimed_job),
    interval '3 minutes'
  ),
  'current owner can renew the lease'
);
select ok(
  not public.renew_job_lease(
    '10000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    interval '3 minutes'
  ),
  'wrong token cannot renew the lease'
);

update public.jobs
set lease_expires_at = pg_catalog.now() - interval '1 second'
where id = '10000000-0000-0000-0000-000000000001';

select is(
  public.requeue_stale_jobs(interval '5 minutes'),
  1,
  'expired lease is requeued'
);
select is(
  (
    select status
    from public.jobs
    where id = '10000000-0000-0000-0000-000000000001'
  ),
  'queued',
  'requeue returns the job to queued'
);
select ok(
  (
    select lease_token is null
      and lease_expires_at is null
      and heartbeat_at is null
      and claimed_at is null
    from public.jobs
    where id = '10000000-0000-0000-0000-000000000001'
  ),
  'requeue clears lease ownership'
);

update public.jobs
set status = 'running',
    claimed_at = pg_catalog.now() - interval '10 minutes',
    lease_token = null,
    lease_expires_at = null
where id = '10000000-0000-0000-0000-000000000001';

select is(
  public.requeue_stale_jobs(interval '5 minutes'),
  1,
  'legacy running row without a lease is recoverable'
);
select throws_ok(
  $$select public.claim_next_job(interval '0 seconds')$$,
  '22023',
  'lease duration must be between 0 seconds and 1 hour',
  'invalid lease duration is rejected'
);

select * from finish();

rollback;
