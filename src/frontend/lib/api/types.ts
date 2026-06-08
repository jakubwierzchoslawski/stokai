export interface ApiEnvelope<T> {
  data?: T;
  meta?: { request_id?: string; elapsed_ms?: number };
  error?: ApiErrorBody;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export type ApiErrorCode =
  | `AUTH_${string}`
  | `VALIDATION_${string}`
  | `RATE_LIMIT_${string}`
  | `COST_LIMIT_${string}`
  | "NOT_FOUND"
  | "EXTERNAL_UNAVAILABLE"
  | "INTERNAL_ERROR"
  | "CONTRACT_MISMATCH"
  | "NETWORK_ERROR"
  | (string & {});
