import type { components } from "./schema";

type HealthResponse = components["schemas"]["HealthResponse"];
type ReadyResponse = components["schemas"]["ReadyResponse"];
type StatusResponse = components["schemas"]["StatusResponse"];
type SummarizeRequest = components["schemas"]["SummarizeRequest"];
type SummarizeResponse = components["schemas"]["SummarizeResponse"];
type SummaryResponse = components["schemas"]["SummaryResponse"];
type SummaryPdfResponse = components["schemas"]["SummaryPdfResponse"];
type JobStatusResponse = components["schemas"]["JobStatusResponse"];
type JobStatus = JobStatusResponse["status"];
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
  HealthResponse,
  JobStatus,
  JobStatusResponse,
  ReadyResponse,
  StatusResponse,
  SummarizeRequest,
  SummarizeResponse,
  CheckoutSessionRequest,
  CheckoutSessionResponse,
  CustomerPortalSessionResponse,
  PackRefundResponse,
  SummaryPdfResponse,
  SummaryResponse,
  PlanResponse,
  BillingAccountResponse,
  BillingOrderHistoryEntry,
  PackBillingState,
  SubscriptionBillingState,
  UsageOverviewResponse,
  UsageHistoryEntry
};
