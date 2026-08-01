create table if not exists public.briefing_stream_leases (
  lease_token uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  client_subject text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  constraint briefing_stream_leases_subject_length check (char_length(client_subject) between 1 and 128)
);

create index if not exists briefing_stream_leases_user_expires_idx
  on public.briefing_stream_leases (user_id, expires_at);
create index if not exists briefing_stream_leases_subject_expires_idx
  on public.briefing_stream_leases (client_subject, expires_at);
create index if not exists briefing_stream_leases_expires_idx
  on public.briefing_stream_leases (expires_at);

alter table public.briefing_stream_leases enable row level security;
revoke all on table public.briefing_stream_leases from public, anon, authenticated, service_role;

create or replace function public.claim_briefing_stream_lease(
  p_user_id uuid,
  p_client_subject text,
  p_max_per_user integer,
  p_max_per_subject integer,
  p_lease_seconds integer
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  claimed_token uuid;
begin
  if p_user_id is null
     or p_client_subject is null
     or char_length(p_client_subject) not between 1 and 128
     or p_max_per_user < 1
     or p_max_per_subject < 1
     or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid stream lease request';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));
  perform pg_advisory_xact_lock(hashtextextended(p_client_subject, 1));

  delete from public.briefing_stream_leases where expires_at <= statement_timestamp();

  if (select count(*) from public.briefing_stream_leases where user_id = p_user_id) >= p_max_per_user
     or (select count(*) from public.briefing_stream_leases where client_subject = p_client_subject) >= p_max_per_subject then
    return null;
  end if;

  insert into public.briefing_stream_leases (user_id, client_subject, expires_at)
  values (p_user_id, p_client_subject, statement_timestamp() + make_interval(secs => p_lease_seconds))
  returning lease_token into claimed_token;
  return claimed_token;
end;
$$;

create or replace function public.renew_briefing_stream_lease(
  p_lease_token uuid,
  p_lease_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if p_lease_token is null or p_lease_seconds not between 30 and 300 then
    return false;
  end if;
  update public.briefing_stream_leases
  set expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds)
  where lease_token = p_lease_token and expires_at > statement_timestamp();
  return found;
end;
$$;

create or replace function public.release_briefing_stream_lease(p_lease_token uuid)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  delete from public.briefing_stream_leases where lease_token = p_lease_token;
  return true;
end;
$$;

revoke all on function public.claim_briefing_stream_lease(uuid, text, integer, integer, integer) from public, anon, authenticated;
revoke all on function public.renew_briefing_stream_lease(uuid, integer) from public, anon, authenticated;
revoke all on function public.release_briefing_stream_lease(uuid) from public, anon, authenticated;
grant execute on function public.claim_briefing_stream_lease(uuid, text, integer, integer, integer) to service_role;
grant execute on function public.renew_briefing_stream_lease(uuid, integer) to service_role;
grant execute on function public.release_briefing_stream_lease(uuid) to service_role;
