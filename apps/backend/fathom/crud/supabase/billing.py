"""Stable billing persistence facade grouped by database responsibility."""

from fathom.crud.supabase.billing_catalog import (
    fetch_active_plans,
    fetch_plan_by_id,
    fetch_plan_by_product_id,
    fetch_plan_names_by_ids,
)
from fathom.crud.supabase.billing_credits import (
    consume_credit_lot_by_id,
    expire_active_subscription_lots,
    fetch_credit_lot_by_source,
    fetch_pack_lots_by_order_ids,
    remaining_seconds_from_lot,
    summarize_credit_lots,
    upsert_credit_lot,
)
from fathom.crud.supabase.billing_entitlements import (
    adjust_entitlement_debt,
    fetch_entitlement,
    update_entitlement_snapshot,
    upsert_subscription_entitlement_state,
)
from fathom.crud.supabase.billing_operations import (
    create_billing_sync_operation,
    fetch_billing_sync_operation,
    resolve_billing_sync_operation,
    resolve_refund_sync_operations,
)
from fathom.crud.supabase.billing_orders import (
    fetch_polar_order_ids_refund_pending,
    list_billing_orders_for_user,
    list_refund_pending_pack_orders,
    list_subscription_entitlements_for_reconciliation,
    schedule_subscription_reconciliation,
)
from fathom.crud.supabase.billing_recovery import (
    begin_pack_refund,
    claim_billing_maintenance_lease,
    get_billing_webhook_diagnostics,
    release_billing_maintenance_lease,
    renew_billing_maintenance_lease,
    reopen_pack_refund,
)
from fathom.crud.supabase.billing_usage import fetch_usage_history, settle_job_usage
from fathom.crud.supabase.billing_webhooks import (
    apply_polar_webhook_transaction,
    reclaim_stale_webhook_processing,
    upsert_polar_customer,
)

__all__ = [
    "adjust_entitlement_debt",
    "apply_polar_webhook_transaction",
    "begin_pack_refund",
    "claim_billing_maintenance_lease",
    "consume_credit_lot_by_id",
    "create_billing_sync_operation",
    "expire_active_subscription_lots",
    "fetch_active_plans",
    "fetch_credit_lot_by_source",
    "fetch_entitlement",
    "fetch_billing_sync_operation",
    "fetch_pack_lots_by_order_ids",
    "fetch_plan_by_id",
    "fetch_plan_by_product_id",
    "fetch_plan_names_by_ids",
    "fetch_polar_order_ids_refund_pending",
    "fetch_usage_history",
    "get_billing_webhook_diagnostics",
    "list_billing_orders_for_user",
    "list_refund_pending_pack_orders",
    "list_subscription_entitlements_for_reconciliation",
    "reclaim_stale_webhook_processing",
    "release_billing_maintenance_lease",
    "remaining_seconds_from_lot",
    "renew_billing_maintenance_lease",
    "reopen_pack_refund",
    "resolve_billing_sync_operation",
    "resolve_refund_sync_operations",
    "schedule_subscription_reconciliation",
    "settle_job_usage",
    "summarize_credit_lots",
    "update_entitlement_snapshot",
    "upsert_credit_lot",
    "upsert_polar_customer",
    "upsert_subscription_entitlement_state",
]
