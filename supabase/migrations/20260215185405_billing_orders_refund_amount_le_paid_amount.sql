-- Ensure refunded totals never exceed paid totals.

update public.billing_orders
set refunded_amount_cents = least(coalesce(refunded_amount_cents, 0), paid_amount_cents);

alter table public.billing_orders
  drop constraint if exists billing_orders_refund_le_paid_check;

alter table public.billing_orders
  add constraint billing_orders_refund_le_paid_check
  check (refunded_amount_cents <= paid_amount_cents);
