import type { components } from "./schema";

type HealthResponse = components["schemas"]["HealthResponse"];
type ReadyResponse = components["schemas"]["ReadyResponse"];
type StatusResponse = components["schemas"]["StatusResponse"];
type BriefingSessionCreateRequest = components["schemas"]["BriefingSessionCreateRequest"];
type BriefingSessionResponse = components["schemas"]["BriefingSessionResponse"];
type BriefingSessionState = BriefingSessionResponse["state"];
type BriefingSessionResolution = BriefingSessionResponse["resolution_type"];
type BriefingResponse = components["schemas"]["BriefingResponse"];
type BriefingPdfResponse = components["schemas"]["BriefingPdfResponse"];
type PlanResponse = components["schemas"]["PlanResponse"];
type UsageOverviewResponse = components["schemas"]["UsageOverviewResponse"];
type UsageHistoryEntry = components["schemas"]["UsageHistoryEntry"];
type BillingAccountResponse = components["schemas"]["BillingAccountResponse"];
type BillingOrderHistoryEntry = components["schemas"]["BillingOrderHistoryEntry"];
type PackBillingState = components["schemas"]["PackBillingState"];
type SubscriptionBillingState = components["schemas"]["SubscriptionBillingState"];
type CheckoutSessionRequest = components["schemas"]["CheckoutSessionRequest"];
type CheckoutSessionResponse = components["schemas"]["CheckoutSessionResponse"];
type CustomerPortalSessionResponse = components["schemas"]["CustomerPortalSessionResponse"];
type PackRefundResponse = components["schemas"]["PackRefundResponse"];

type ErrorResponse = components["schemas"]["ErrorResponse"];
type HTTPValidationError = components["schemas"]["HTTPValidationError"];

type ApiErrorBody = ErrorResponse | HTTPValidationError;

export type {
  ApiErrorBody,
  BriefingPdfResponse,
  BriefingResponse,
  BriefingSessionCreateRequest,
  BriefingSessionResolution,
  BriefingSessionResponse,
  BriefingSessionState,
  HealthResponse,
  ReadyResponse,
  StatusResponse,
  CheckoutSessionRequest,
  CheckoutSessionResponse,
  CustomerPortalSessionResponse,
  PackRefundResponse,
  PlanResponse,
  BillingAccountResponse,
  BillingOrderHistoryEntry,
  PackBillingState,
  SubscriptionBillingState,
  UsageOverviewResponse,
  UsageHistoryEntry
};
