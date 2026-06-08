/* Only this file is allowed to call fetch against /api */
import { env } from "../env";
import { ApiError } from "./errors";
import type { ApiEnvelope, ApiErrorBody } from "./types";

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function clearAccessToken(): void {
  accessToken = null;
}

interface ApiInit extends RequestInit {
  skipAuth?: boolean;
  _retry?: boolean;
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const url = env.apiBaseUrl.replace(/\/$/, "") + (path.startsWith("/") ? path : `/${path}`);

  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body && !(init.body instanceof FormData)) {
    headers.set("content-type", "application/json");
  }
  if (!init.skipAuth && accessToken) {
    headers.set("authorization", `Bearer ${accessToken}`);
  }
  headers.set("accept", "application/json");

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: "include" });
  } catch (err) {
    throw new ApiError(0, "NETWORK_ERROR", err instanceof Error ? err.message : "Network error");
  }

  if (response.status === 401 && !init._retry && !init.skipAuth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return api<T>(path, { ...init, _retry: true });
    }
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }

  let body: ApiEnvelope<T> | null = null;
  if (response.status !== 204) {
    try {
      body = (await response.json()) as ApiEnvelope<T>;
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const errBody: ApiErrorBody = body?.error ?? {
      code: "INTERNAL_ERROR",
      message: `Request failed: ${response.status} ${response.statusText}`,
    };
    throw new ApiError(
      response.status,
      errBody.code,
      errBody.message,
      errBody.details,
      errBody.request_id,
    );
  }

  return (body?.data ?? (undefined as unknown)) as T;
}

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const url = env.apiBaseUrl.replace(/\/$/, "") + "/auth/refresh";
      const resp = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { accept: "application/json" },
      });
      if (!resp.ok) return false;
      const body = (await resp.json()) as ApiEnvelope<{ access_token: string; exp: number }>;
      if (!body.data?.access_token) return false;
      accessToken = body.data.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export function __resetForTests() {
  accessToken = null;
  refreshInFlight = null;
}
