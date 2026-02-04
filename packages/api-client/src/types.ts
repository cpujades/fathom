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
type CheckoutSessionRequest = components["schemas"]["CheckoutSessionRequest"];
type CheckoutSessionResponse = components["schemas"]["CheckoutSessionResponse"];

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
  SummaryPdfResponse,
  SummaryResponse,
  PlanResponse,
  UsageOverviewResponse,
  UsageHistoryEntry
};
