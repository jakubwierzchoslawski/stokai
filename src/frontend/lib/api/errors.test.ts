import { describe, it, expect } from "vitest";
import {
  ApiError,
  isAuthError,
  isValidationError,
  isRateLimit,
  isCostLimit,
  isNotFound,
  isExternalUnavailable,
} from "./errors";

describe("ApiError", () => {
  it("carries status, code, message, details, requestId", () => {
    const err = new ApiError(401, "AUTH_INVALID_CREDENTIALS", "bad", { field: "password" }, "req-1");
    expect(err.status).toBe(401);
    expect(err.code).toBe("AUTH_INVALID_CREDENTIALS");
    expect(err.message).toBe("bad");
    expect(err.details).toEqual({ field: "password" });
    expect(err.requestId).toBe("req-1");
    expect(err).toBeInstanceOf(Error);
  });

  it.each([
    ["AUTH_INVALID_CREDENTIALS", isAuthError, true],
    ["VALIDATION_FORMAT", isValidationError, true],
    ["RATE_LIMIT_USER", isRateLimit, true],
    ["COST_LIMIT_DAILY", isCostLimit, true],
    ["NOT_FOUND", isNotFound, true],
    ["EXTERNAL_UNAVAILABLE", isExternalUnavailable, true],
    ["INTERNAL_ERROR", isAuthError, false],
  ])("predicate %s -> %s = %s", (code, fn, expected) => {
    const err = new ApiError(500, code, "x");
    expect(fn(err)).toBe(expected);
  });
});
