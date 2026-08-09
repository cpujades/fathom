-- Keep subscription rollover bounded to the immediately preceding cycle.
-- Historical migration 20260729143000 remains immutable; this forward
-- migration replaces the webhook command for already-deployed databases.

create or replace function public.apply_polar_webhook_event(
  p_event_id text,
  p_event_type text,
  p_event_at timestamptz,
  p_resource_type text,
  p_resource_id text,
  p_payload jsonb,
  p_debt_cap_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  event_row public.billing_webhook_events;
  order_row public.billing_orders;
  plan_row public.plans;
  entitlement_row public.entitlements;
  lot_row public.credit_lots;
  deferred_event public.billing_webhook_events;
  effective_event_at timestamptz := coalesce(p_event_at, pg_catalog.now());
  event_outcome text := 'applied';
  target_user_id uuid;
  target_order_id text;
  target_product_id text;
  target_subscription_id text;
  target_subscription_status text;
  target_period_start timestamptz;
  target_period_end timestamptz;
  target_source_key text;
  quota_seconds integer;
  rollover_cap_seconds integer;
  rollover_seconds integer := 0;
  current_subscription_remaining integer := 0;
  lot_created boolean := false;
  order_was_terminal boolean := false;
  provider_total_refunded integer;
  refund_delta_cents integer;
begin
  if p_event_id is null or pg_catalog.btrim(p_event_id) = '' then
    raise exception 'provider event id is required' using errcode = '22023';
  end if;
  if p_event_type is null or pg_catalog.btrim(p_event_type) = '' then
    raise exception 'provider event type is required' using errcode = '22023';
  end if;
  if p_payload is null or pg_catalog.jsonb_typeof(p_payload) <> 'object' then
    raise exception 'normalized event payload must be an object' using errcode = '22023';
  end if;
  if p_debt_cap_seconds is null or p_debt_cap_seconds < 0 then
    raise exception 'debt cap seconds cannot be negative' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'polar:' || coalesce(p_resource_type, 'event') || ':' || coalesce(p_resource_id, p_event_id),
      0
    )
  );

  insert into public.billing_webhook_events (
    event_id,
    provider,
    event_type,
    payload,
    status,
    provider_event_at,
    resource_type,
    resource_id
  )
  values (
    p_event_id,
    'polar',
    p_event_type,
    p_payload - 'email',
    'received',
    effective_event_at,
    p_resource_type,
    p_resource_id
  )
  on conflict (event_id) do nothing;

  select *
  into event_row
  from public.billing_webhook_events
  where event_id = p_event_id
  for update;

  if event_row.provider <> 'polar'
    or event_row.event_type <> p_event_type
    or event_row.resource_type is distinct from p_resource_type
    or event_row.resource_id is distinct from p_resource_id
  then
    raise exception 'provider event id was reused with different event facts'
      using errcode = '23505';
  end if;

  if event_row.status = 'processed' then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'already_processed',
      'outcome', coalesce(event_row.payload ->> 'outcome', 'applied')
    );
  end if;

  update public.billing_webhook_events
  set status = 'processing',
      error = null,
      processed_at = null
  where event_id = p_event_id;

  begin
    if p_event_type in ('customer.created', 'customer.state_changed') then
      if p_payload ->> 'user_id' is null then
        event_outcome := 'ignored_missing_external_id';
      else
        target_user_id := (p_payload ->> 'user_id')::uuid;

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
        where public.polar_customers.provider_event_at is null
          or (excluded.provider_event_at, excluded.provider_event_id)
            > (public.polar_customers.provider_event_at, public.polar_customers.provider_event_id);

        if not found then
          event_outcome := 'stale_ignored';
        end if;
      end if;

    elsif p_event_type = 'order.paid' then
      target_order_id := p_payload ->> 'order_id';
      target_user_id := (p_payload ->> 'user_id')::uuid;
      target_product_id := p_payload ->> 'product_id';

      select *
      into plan_row
      from public.plans
      where polar_product_id = target_product_id
      limit 1;
      if not found then
        raise exception 'plan not found for Polar product id' using errcode = 'P0002';
      end if;

      select *
      into order_row
      from public.billing_orders
      where polar_order_id = target_order_id
      for update;
      order_was_terminal := found and order_row.status in ('refund_pending', 'refunded');

      insert into public.billing_orders (
        polar_order_id,
        user_id,
        plan_id,
        plan_type,
        polar_product_id,
        polar_subscription_id,
        currency,
        paid_amount_cents,
        status
      )
      values (
        target_order_id,
        target_user_id,
        plan_row.id,
        plan_row.plan_type,
        target_product_id,
        p_payload ->> 'subscription_id',
        lower(coalesce(p_payload ->> 'currency', plan_row.currency, 'usd')),
        greatest(coalesce((p_payload ->> 'paid_amount_cents')::integer, 0), 0),
        'paid'
      )
      on conflict (polar_order_id) do update
      set user_id = excluded.user_id,
          plan_id = excluded.plan_id,
          plan_type = excluded.plan_type,
          polar_product_id = excluded.polar_product_id,
          polar_subscription_id = excluded.polar_subscription_id,
          currency = excluded.currency,
          paid_amount_cents = excluded.paid_amount_cents,
          status = case
            when public.billing_orders.status in ('refund_pending', 'refunded')
              then public.billing_orders.status
            else 'paid'
          end,
          updated_at = pg_catalog.now()
      returning * into order_row;

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

      if plan_row.plan_type = 'pack' and not order_was_terminal then
        insert into public.credit_lots (
          user_id,
          plan_id,
          lot_type,
          source_key,
          granted_seconds,
          pack_expires_at,
          status
        )
        values (
          target_user_id,
          plan_row.id,
          'pack_order',
          target_order_id,
          greatest(coalesce(plan_row.quota_seconds, 0), 0),
          pg_catalog.now() + pg_catalog.make_interval(days => coalesce(plan_row.pack_expiry_days, 0)),
          'active'
        )
        on conflict (lot_type, source_key) do nothing
        returning * into lot_row;
        lot_created := found;

        if lot_created then
          perform public.pay_down_billing_debt_from_lot(
            target_user_id,
            lot_row.id,
            p_debt_cap_seconds
          );
        end if;
      end if;

      for deferred_event in
        select *
        from public.billing_webhook_events
        where provider = 'polar'
          and event_type = 'order.refunded'
          and resource_type = 'order'
          and resource_id = target_order_id
          and status = 'deferred'
        order by provider_event_at, event_id
        for update
      loop
        perform public.apply_polar_order_refund(
          target_order_id,
          (deferred_event.payload ->> 'provider_total_refunded')::integer,
          coalesce((deferred_event.payload ->> 'refund_delta_cents')::integer, 0)
        );

        update public.billing_webhook_events
        set status = 'processed',
            processed_at = pg_catalog.now(),
            error = null,
            payload = payload || pg_catalog.jsonb_build_object('outcome', 'applied_after_defer')
        where event_id = deferred_event.event_id;
      end loop;

      perform public.refresh_billing_entitlement_snapshot(target_user_id, p_debt_cap_seconds);

    elsif p_event_type = 'order.refunded' then
      target_order_id := p_payload ->> 'order_id';
      if target_order_id is null or pg_catalog.btrim(target_order_id) = '' then
        raise exception 'Polar refund payload is missing order id'
          using errcode = '22023';
      end if;
      provider_total_refunded := (p_payload ->> 'provider_total_refunded')::integer;
      refund_delta_cents := coalesce((p_payload ->> 'refund_delta_cents')::integer, 0);
      target_user_id := public.apply_polar_order_refund(
        target_order_id,
        provider_total_refunded,
        refund_delta_cents
      );

      if target_user_id is null then
        update public.billing_webhook_events
        set status = 'deferred',
            processed_at = null,
            error = 'waiting for referenced order',
            payload = payload || pg_catalog.jsonb_build_object('outcome', 'deferred_unknown_order')
        where event_id = p_event_id;

        return pg_catalog.jsonb_build_object(
          'resolution_type', 'deferred',
          'outcome', 'waiting_for_order'
        );
      end if;

      perform public.refresh_billing_entitlement_snapshot(target_user_id, p_debt_cap_seconds);

    elsif p_event_type in (
      'subscription.created',
      'subscription.active',
      'subscription.uncanceled',
      'subscription.canceled',
      'subscription.past_due',
      'subscription.updated',
      'subscription.revoked'
    ) then
      target_user_id := (p_payload ->> 'user_id')::uuid;
      target_product_id := p_payload ->> 'product_id';
      target_subscription_id := p_payload ->> 'subscription_id';
      target_subscription_status := coalesce(p_payload ->> 'status', 'unknown');
      target_period_start := (p_payload ->> 'period_start')::timestamptz;
      target_period_end := (p_payload ->> 'period_end')::timestamptz;

      select *
      into plan_row
      from public.plans
      where polar_product_id = target_product_id
      limit 1;
      if not found then
        raise exception 'plan not found for Polar product id' using errcode = 'P0002';
      end if;

      insert into public.entitlements (user_id)
      values (target_user_id)
      on conflict (user_id) do nothing;

      select *
      into entitlement_row
      from public.entitlements
      where public.entitlements.user_id = target_user_id
      for update;

      if entitlement_row.provider_event_at is not null
        and (effective_event_at, p_event_id)
          <= (entitlement_row.provider_event_at, entitlement_row.provider_event_id)
      then
        event_outcome := 'stale_ignored';
      else
        quota_seconds := greatest(coalesce(plan_row.quota_seconds, 0), 0);
        rollover_cap_seconds := greatest(coalesce(plan_row.rollover_cap_seconds, 0), 0);

        update public.credit_lots
        set status = 'expired',
            updated_at = pg_catalog.now()
        where public.credit_lots.user_id = target_user_id
          and public.credit_lots.lot_type = 'pack_order'
          and status = 'active'
          and pack_expires_at is not null
          and pack_expires_at <= pg_catalog.now();

        if p_event_type = 'subscription.revoked'
          or target_subscription_status in ('revoked', 'ended', 'inactive')
        then
          rollover_seconds := 0;
          update public.credit_lots
          set status = 'expired',
              updated_at = pg_catalog.now()
          where public.credit_lots.user_id = target_user_id
            and lot_type = 'subscription_cycle'
            and status = 'active';
        elsif target_period_start is not null and target_period_end is not null then
          target_source_key := coalesce(
              target_subscription_id,
              'user:' || target_user_id::text
            )
            || ':' || (p_payload ->> 'period_start');

          select *
          into lot_row
          from public.credit_lots
          where lot_type = 'subscription_cycle'
            and public.credit_lots.source_key = target_source_key
          for update;

          if found then
            select coalesce(
              sum(greatest(granted_seconds - consumed_seconds - revoked_seconds, 0)),
              0
            )::integer
            into rollover_seconds
            from public.credit_lots
            where public.credit_lots.user_id = target_user_id
              and lot_type = 'subscription_cycle'
              and source_key = target_source_key || ':rollover';
          else
            if entitlement_row.subscription_plan_id = plan_row.id
              and target_product_id <> 'internal_free'
              and entitlement_row.period_end = target_period_start
            then
              -- Only the immediately preceding billing cycle may roll forward.
              -- The plan cap equals one monthly grant, so the new cycle can
              -- never exceed twice its normal allowance.
              select coalesce(
                sum(greatest(granted_seconds - consumed_seconds - revoked_seconds, 0)),
                0
              )::integer
              into current_subscription_remaining
              from public.credit_lots
              where public.credit_lots.user_id = target_user_id
                and lot_type = 'subscription_cycle'
                and plan_id = plan_row.id
                and pack_expires_at = target_period_start
                and source_key not like '%:rollover'
                and status in ('active', 'expired');
              rollover_seconds := least(current_subscription_remaining, rollover_cap_seconds);
            else
              rollover_seconds := 0;
            end if;

            update public.credit_lots
            set status = 'expired',
                updated_at = pg_catalog.now()
            where public.credit_lots.user_id = target_user_id
              and lot_type = 'subscription_cycle'
              and status = 'active';

            if rollover_seconds > 0 then
              insert into public.credit_lots (
                user_id,
                plan_id,
                lot_type,
                source_key,
                granted_seconds,
                pack_expires_at,
                status
              )
              values (
                target_user_id,
                plan_row.id,
                'subscription_cycle',
                target_source_key || ':rollover',
                rollover_seconds,
                target_period_end,
                'active'
              )
              on conflict (lot_type, source_key) do nothing
              returning * into lot_row;

              if found then
                perform public.pay_down_billing_debt_from_lot(
                  target_user_id,
                  lot_row.id,
                  p_debt_cap_seconds
                );
              end if;
            end if;

            insert into public.credit_lots (
              user_id,
              plan_id,
              lot_type,
              source_key,
              granted_seconds,
              pack_expires_at,
              status
            )
            values (
              target_user_id,
              plan_row.id,
              'subscription_cycle',
              target_source_key,
              quota_seconds,
              target_period_end,
              'active'
            )
            on conflict (lot_type, source_key) do nothing
            returning * into lot_row;

            if found then
              perform public.pay_down_billing_debt_from_lot(
                target_user_id,
                lot_row.id,
                p_debt_cap_seconds
              );
            end if;
          end if;
        end if;

        update public.entitlements
        set subscription_plan_id = plan_row.id,
            subscription_status = target_subscription_status,
            period_start = target_period_start,
            period_end = target_period_end,
            subscription_cycle_grant_seconds = quota_seconds,
            subscription_rollover_seconds = rollover_seconds,
            subscription_available_seconds = greatest(quota_seconds + rollover_seconds, 0),
            polar_subscription_id = target_subscription_id,
            provider_event_at = effective_event_at,
            provider_event_id = p_event_id,
            updated_at = pg_catalog.now()
        where public.entitlements.user_id = target_user_id;

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

        perform public.refresh_billing_entitlement_snapshot(target_user_id, p_debt_cap_seconds);
      end if;

    else
      event_outcome := 'ignored';
    end if;

    update public.billing_webhook_events
    set status = 'processed',
        processed_at = pg_catalog.now(),
        error = null,
        payload = payload || pg_catalog.jsonb_build_object('outcome', event_outcome)
    where event_id = p_event_id;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'processed',
      'outcome', event_outcome
    );
  exception
    when others then
      update public.billing_webhook_events
      set status = 'failed',
          processed_at = pg_catalog.now(),
          error = pg_catalog.left(sqlerrm, 1000)
      where event_id = p_event_id;

      return pg_catalog.jsonb_build_object(
        'resolution_type', 'failed',
        'outcome', 'rolled_back',
        'error', pg_catalog.left(sqlerrm, 300)
      );
  end;
end;
$$;
