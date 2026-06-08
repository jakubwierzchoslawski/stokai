import type { ApiErrorCode } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    details?: Record<string, unknown>,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export const isAuthError = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("AUTH_");
export const isValidationError = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("VALIDATION_");
export const isRateLimit = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("RATE_LIMIT_");
export const isCostLimit = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code.startsWith("COST_LIMIT_");
export const isNotFound = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "NOT_FOUND";
export const isExternalUnavailable = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "EXTERNAL_UNAVAILABLE";
export const isTokenExpired = (e: unknown): e is ApiError =>
  e instanceof ApiError && e.code === "AUTH_TOKEN_EXPIRED";
