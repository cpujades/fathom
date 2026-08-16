-- Reset mutable test data and harden the schema before the first real users.
--
-- Keep:
-- - public.plans rows;
-- - Storage bucket definitions and policies;
-- - Auth and provider configuration; and
-- - migration history.
--
-- Storage objects, Auth users, and Polar customers are provider resources.
-- The guarded reset script deletes those through their APIs.

truncate table
  public.briefing_publications,
  public.job_events,
  public.usage_settlements,
  public.billing_sync_operations,
  public.billing_webhook_events,
  public.billing_orders,
  public.credit_lots,
  public.entitlements,
  public.polar_customers,
  public.briefing_stream_leases,
  public.billing_maintenance_leases,
  public.api_rate_limit_buckets,
  public.jobs,
  public.summaries,
  public.transcript_segments,
  public.transcripts
restart identity;

-- Summaries are a server-only global cache. The user id still validates the
-- producer job, but it is not stored as summary ownership.
create or replace function public.prepare_summary(
  p_summary_id uuid,
  p_user_id uuid,
  p_job_id uuid,
  p_generation_token uuid,
  p_transcript_id uuid,
  p_prompt_key text,
  p_summary_model text
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  summary_row public.summaries;
begin
  if p_summary_id is null
    or p_user_id is null
    or p_job_id is null
    or p_generation_token is null
    or p_transcript_id is null
  then
    raise exception 'summary, user, job, generation token, and transcript ids are required'
      using errcode = '22023';
  end if;
  if p_prompt_key is null or pg_catalog.btrim(p_prompt_key) = '' then
    raise exception 'prompt key is required' using errcode = '22023';
  end if;
  if p_summary_model is null or pg_catalog.btrim(p_summary_model) = '' then
    raise exception 'summary model is required' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      p_transcript_id::text || ':' || p_prompt_key || ':' || p_summary_model,
      0
    )
  );

  if not exists (
    select 1
    from public.jobs
    where id = p_job_id
      and user_id = p_user_id
      and status = 'running'
      and lease_token = p_generation_token
      and lease_expires_at > pg_catalog.now()
  ) then
    raise exception 'summary producer must hold the current live job lease'
      using errcode = '55000';
  end if;

  select *
  into summary_row
  from public.summaries
  where transcript_id = p_transcript_id
    and prompt_key = p_prompt_key
    and summary_model = p_summary_model
  limit 1
  for update;

  if not found then
    insert into public.summaries (
      id,
      transcript_id,
      prompt_key,
      summary_model,
      summary_markdown,
      pdf_object_key,
      status,
      status_updated_at,
      ready_at,
      failed_at,
      generation_job_id,
      generation_token
    )
    values (
      p_summary_id,
      p_transcript_id,
      p_prompt_key,
      p_summary_model,
      '',
      null,
      'pending',
      pg_catalog.now(),
      null,
      null,
      p_job_id,
      p_generation_token
    )
    returning * into summary_row;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'created',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  if summary_row.status = 'ready' then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'ready',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  if summary_row.status = 'pending'
    and exists (
      select 1
      from public.jobs
      where id = summary_row.generation_job_id
        and status = 'running'
        and lease_token = summary_row.generation_token
        and lease_expires_at > pg_catalog.now()
    )
  then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'in_progress',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  update public.summaries as summary
  set summary_markdown = '',
      pdf_object_key = null,
      status = 'pending',
      status_updated_at = pg_catalog.now(),
      ready_at = null,
      failed_at = null,
      generation_job_id = p_job_id,
      generation_token = p_generation_token
  where id = summary_row.id
  returning * into summary_row;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'taken_over',
    'summary', pg_catalog.to_jsonb(summary_row)
  );
end;
$$;

revoke all on function public.prepare_summary(uuid, uuid, uuid, uuid, uuid, text, text)
  from public, anon, authenticated;
grant execute on function public.prepare_summary(uuid, uuid, uuid, uuid, uuid, text, text)
  to service_role;

-- The latest billing functions are intentionally transformed from the exact
-- preceding migration state. This keeps one linear definition of the complex
-- settlement and webhook logic while changing only the approved columns.
do $migration$
declare
  function_signature regprocedure;
  function_definition text;
  old_customer_event text := $old_customer_event$
        insert into public.polar_customers (
          user_id,
          external_customer_id,
          polar_customer_id,
          email,
          country,
          provider_event_at,
          provider_event_id
        )
        values (
          target_user_id,
          p_payload ->> 'external_customer_id',
          p_payload ->> 'customer_id',
          p_payload ->> 'email',
          p_payload ->> 'country',
          effective_event_at,
          p_event_id
        )
        on conflict (user_id) do update
        set external_customer_id = excluded.external_customer_id,
            polar_customer_id = coalesce(excluded.polar_customer_id, public.polar_customers.polar_customer_id),
            email = coalesce(excluded.email, public.polar_customers.email),
            country = coalesce(excluded.country, public.polar_customers.country),
            provider_event_at = excluded.provider_event_at,
            provider_event_id = excluded.provider_event_id,
            updated_at = pg_catalog.now()
$old_customer_event$;
  new_customer_event text := $new_customer_event$
        insert into public.polar_customers (
          user_id,
          external_customer_id,
          polar_customer_id,
          provider_event_at,
          provider_event_id
        )
        values (
          target_user_id,
          p_payload ->> 'external_customer_id',
          p_payload ->> 'customer_id',
          effective_event_at,
          p_event_id
        )
        on conflict (user_id) do update
        set external_customer_id = excluded.external_customer_id,
            polar_customer_id = coalesce(excluded.polar_customer_id, public.polar_customers.polar_customer_id),
            provider_event_at = excluded.provider_event_at,
            provider_event_id = excluded.provider_event_id,
            updated_at = pg_catalog.now()
$new_customer_event$;
  old_order_customer text := $old_order_customer$
      insert into public.polar_customers (
        user_id,
        external_customer_id,
        polar_customer_id,
        email
      )
      values (
        target_user_id,
        target_user_id::text,
        p_payload ->> 'customer_id',
        p_payload ->> 'email'
      )
      on conflict (user_id) do update
      set polar_customer_id = coalesce(
            public.polar_customers.polar_customer_id,
            excluded.polar_customer_id
          ),
          email = coalesce(public.polar_customers.email, excluded.email),
          updated_at = pg_catalog.now();
$old_order_customer$;
  new_order_customer text := $new_order_customer$
      insert into public.polar_customers (
        user_id,
        external_customer_id,
        polar_customer_id
      )
      values (
        target_user_id,
        target_user_id::text,
        p_payload ->> 'customer_id'
      )
      on conflict (user_id) do update
      set polar_customer_id = coalesce(
            public.polar_customers.polar_customer_id,
            excluded.polar_customer_id
          ),
          updated_at = pg_catalog.now();
$new_order_customer$;
begin
  foreach function_signature in array array[
    'public.settle_job_usage(uuid,uuid,integer)'::regprocedure,
    'public.refresh_billing_entitlement_snapshot(uuid,integer)'::regprocedure
  ]
  loop
    function_definition := pg_catalog.pg_get_functiondef(function_signature::oid);
    if pg_catalog.strpos(function_definition, 'pack_expires_at') = 0 then
      raise exception 'expected expiry column was not found in %', function_signature;
    end if;
    function_definition := pg_catalog.replace(
      function_definition,
      'pack_expires_at',
      'expires_at'
    );
    -- The entitlement snapshot keeps its API-facing pack expiry field. Only
    -- credit_lots uses the shorter expires_at name.
    function_definition := pg_catalog.replace(
      function_definition,
      'expires_at = next_pack_expiry',
      'pack_expires_at = next_pack_expiry'
    );
    execute function_definition;
  end loop;

  function_signature :=
    'public.apply_polar_webhook_event(text,text,timestamptz,text,text,jsonb,integer)'::regprocedure;
  function_definition := pg_catalog.pg_get_functiondef(function_signature::oid);

  if pg_catalog.strpos(function_definition, old_customer_event) = 0
    or pg_catalog.strpos(function_definition, old_order_customer) = 0
    or pg_catalog.strpos(function_definition, 'pack_expires_at') = 0
  then
    raise exception 'the preceding Polar webhook definition does not match the expected migration state';
  end if;

  function_definition := pg_catalog.replace(
    function_definition,
    old_customer_event,
    new_customer_event
  );
  function_definition := pg_catalog.replace(
    function_definition,
    old_order_customer,
    new_order_customer
  );
  function_definition := pg_catalog.replace(
    function_definition,
    'pack_expires_at',
    'expires_at'
  );
  function_definition := pg_catalog.replace(
    function_definition,
    'expires_at = next_pack_expiry',
    'pack_expires_at = next_pack_expiry'
  );

  if pg_catalog.strpos(function_definition, 'public.polar_customers.email') > 0
    or pg_catalog.strpos(function_definition, 'public.polar_customers.country') > 0
    or pg_catalog.strpos(function_definition, 'excluded.email') > 0
    or pg_catalog.strpos(function_definition, 'excluded.country') > 0
  then
    raise exception 'Polar customer PII references remain in the webhook function';
  end if;

  execute function_definition;
end;
$migration$;

drop index if exists public.summaries_user_id_idx;
drop index if exists public.summaries_ttl_expires_at_idx;
drop index if exists public.transcripts_ttl_expires_at_idx;
drop index if exists public.polar_customers_email_idx;

alter table public.summaries
  drop column user_id,
  drop column ttl_expires_at,
  alter column summary_model set not null;

alter table public.transcripts
  drop column ttl_expires_at,
  alter column provider_model set not null;

alter table public.polar_customers
  drop column email,
  drop column country;

alter table public.credit_lots
  rename column pack_expires_at to expires_at;

alter table public.entitlements
  alter column pack_available_seconds set default 0,
  alter column pack_available_seconds set not null;

alter table public.jobs
  alter column stage set not null,
  alter column progress set not null,
  alter column status_message set not null;

-- User-owned roots reference Supabase Auth. Shared cache rows do not.
alter table public.jobs
  add constraint jobs_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete cascade,
  add constraint jobs_id_user_id_key unique (id, user_id);

alter table public.entitlements
  add constraint entitlements_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.credit_lots
  add constraint credit_lots_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.polar_customers
  add constraint polar_customers_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete cascade;

alter table public.briefing_stream_leases
  add constraint briefing_stream_leases_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete cascade;

-- Commerce records can outlive an Auth account for refunds and provider audit.
alter table public.billing_orders
  alter column user_id drop not null,
  add constraint billing_orders_user_id_fkey
    foreign key (user_id) references auth.users (id) on delete set null;

-- A settlement is the immutable one-to-one usage record for its job.
alter table public.usage_settlements
  drop constraint usage_settlements_job_id_fkey,
  drop constraint usage_settlements_job_id_key,
  drop constraint usage_settlements_pkey,
  drop column id,
  add constraint usage_settlements_pkey primary key (job_id),
  add constraint usage_settlements_job_owner_fkey
    foreign key (job_id, user_id)
    references public.jobs (id, user_id)
    on delete cascade;

-- The publication owner must be the owner of its source job.
alter table public.briefing_publications
  drop constraint briefing_publications_owner_job_id_fkey,
  add constraint briefing_publications_owner_job_fkey
    foreign key (owner_job_id, owner_user_id)
    references public.jobs (id, user_id)
    on delete cascade;

-- Content and lifecycle checks.
alter table public.transcripts
  add constraint transcripts_url_hash_not_empty
    check (pg_catalog.btrim(url_hash) <> ''),
  add constraint transcripts_text_not_empty
    check (pg_catalog.btrim(transcript_text) <> ''),
  add constraint transcripts_provider_model_not_empty
    check (pg_catalog.btrim(provider_model) <> ''),
  add constraint transcripts_source_counts_nonnegative
    check (
      (source_views is null or source_views >= 0)
      and (source_likes is null or source_likes >= 0)
      and (source_length_seconds is null or source_length_seconds >= 0)
    );

alter table public.summaries
  add constraint summaries_prompt_key_not_empty
    check (pg_catalog.btrim(prompt_key) <> ''),
  add constraint summaries_model_not_empty
    check (pg_catalog.btrim(summary_model) <> '');

alter table public.jobs
  add constraint jobs_url_not_empty
    check (pg_catalog.btrim(url) <> ''),
  add constraint jobs_attempt_count_nonnegative
    check (attempt_count >= 0),
  add constraint jobs_progress_range
    check (progress between 0 and 100),
  add constraint jobs_duration_nonnegative
    check (duration_seconds is null or duration_seconds >= 0),
  add constraint jobs_stage_not_empty
    check (pg_catalog.btrim(stage) <> ''),
  add constraint jobs_status_message_not_empty
    check (pg_catalog.btrim(status_message) <> '');

alter table public.plans
  add constraint plans_name_not_empty
    check (pg_catalog.btrim(name) <> ''),
  add constraint plans_code_not_empty
    check (plan_code = pg_catalog.btrim(plan_code) and pg_catalog.btrim(plan_code) <> ''),
  add constraint plans_currency_format
    check (currency = pg_catalog.lower(currency) and currency ~ '^[a-z]{3}$'),
  add constraint plans_version_positive
    check (version > 0),
  add constraint plans_shape_check
    check (
      quota_seconds is not null
      and quota_seconds > 0
      and (not is_active or polar_product_id is not null)
      and (
        (
          plan_type = 'subscription'
          and rollover_cap_seconds is not null
          and pack_expiry_days is null
          and billing_interval = 'month'
        )
        or (
          plan_type = 'pack'
          and rollover_cap_seconds is null
          and pack_expiry_days is not null
          and pack_expiry_days > 0
          and billing_interval is null
        )
      )
    );

alter table public.polar_customers
  add constraint polar_customers_external_id_not_empty
    check (pg_catalog.btrim(external_customer_id) <> ''),
  add constraint polar_customers_provider_event_pair
    check (
      (provider_event_at is null and provider_event_id is null)
      or (provider_event_at is not null and provider_event_id is not null)
    );

alter table public.billing_webhook_events
  add constraint billing_webhook_events_provider_not_empty
    check (pg_catalog.btrim(provider) <> ''),
  add constraint billing_webhook_events_type_not_empty
    check (pg_catalog.btrim(event_type) <> ''),
  add constraint billing_webhook_events_status_check
    check (status in ('received', 'processing', 'processed', 'failed', 'deferred'));

alter table public.billing_orders
  add constraint billing_orders_currency_format
    check (currency = pg_catalog.lower(currency) and currency ~ '^[a-z]{3}$');

alter table public.entitlements
  add constraint entitlements_period_order_check
    check (
      (period_start is null and period_end is null)
      or (period_start is not null and period_end is not null and period_end > period_start)
    ),
  add constraint entitlements_provider_event_pair
    check (
      (provider_event_at is null and provider_event_id is null)
      or (provider_event_at is not null and provider_event_id is not null)
    );

alter table public.credit_lots
  add constraint credit_lots_expiry_check
    check (lot_type = 'adjustment' or expires_at is not null);

alter table public.briefing_stream_leases
  add constraint briefing_stream_leases_expiry_check
    check (expires_at > created_at);

alter table public.api_rate_limit_buckets
  add constraint api_rate_limit_buckets_subject_not_empty
    check (pg_catalog.btrim(subject) <> ''),
  add constraint api_rate_limit_buckets_scope_not_empty
    check (pg_catalog.btrim(scope) <> '');

-- Query-driven indexes. B-tree indexes can scan in either direction.
drop index if exists public.jobs_duration_seconds_idx;
drop index if exists public.plans_plan_type_idx;
drop index if exists public.transcripts_video_id_idx;
drop index if exists public.usage_settlements_user_settled_idx;
drop index if exists public.polar_customers_polar_customer_id_idx;
drop index if exists public.billing_orders_user_id_idx;
drop index if exists public.briefing_publications_explore_idx;

create index jobs_briefing_library_idx
  on public.jobs (user_id, created_at desc, id desc)
  where status in ('queued', 'running', 'succeeded', 'failed');

create index jobs_user_summary_access_idx
  on public.jobs (user_id, summary_id, created_at desc, id desc)
  where status in ('succeeded', 'deleted') and summary_id is not null;

create index transcripts_video_model_idx
  on public.transcripts (video_id, provider_model)
  where video_id is not null;

create index usage_settlements_user_settled_idx
  on public.usage_settlements (user_id, settled_at desc, job_id desc);

create unique index polar_customers_polar_customer_id_key
  on public.polar_customers (polar_customer_id)
  where polar_customer_id is not null;

create index billing_orders_user_id_idx
  on public.billing_orders (user_id, created_at desc, id desc)
  where user_id is not null;

create index billing_orders_refund_pending_idx
  on public.billing_orders (user_id, created_at desc, id desc)
  where user_id is not null and status = 'refund_pending';

create index briefing_publications_explore_idx
  on public.briefing_publications (topic, listed_at desc, id desc)
  where visibility = 'listed' and moderation_status = 'clear';

create index briefing_publications_explore_all_idx
  on public.briefing_publications (listed_at desc, id desc)
  where visibility = 'listed' and moderation_status = 'clear';

comment on table public.summaries is
  'Server-only global summary cache. User access is authorized through tenant-owned jobs and projected by FastAPI.';
comment on column public.credit_lots.expires_at is
  'Expiry for subscription-cycle and pack lots; adjustment lots may be permanent.';
comment on table public.usage_settlements is
  'One immutable, lease-fenced usage record per job; also the user-facing usage history source.';
