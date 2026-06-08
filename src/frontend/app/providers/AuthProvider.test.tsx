import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen, act } from "@testing-library/react";
import { server } from "../../../../tests/frontend/msw/server";
import { AuthProvider, useAuth } from "./AuthProvider";
import { QueryProvider } from "./QueryProvider";

function Harness() {
  const { state, login, logout } = useAuth();
  return (
    <div>
      <div data-testid="status">{state.status}</div>
      <div data-testid="email">{state.status === "authenticated" ? state.user.email : ""}</div>
      <button onClick={() => login("a@b.com", "pw")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function wrap() {
  return render(
    <QueryProvider>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </QueryProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ error: { code: "AUTH_REFRESH_FAILED", message: "no cookie" } }, { status: 401 }),
      ),
    );
  });

  it("starts in loading and resolves to anonymous when refresh fails on mount", async () => {
    wrap();
    expect(screen.getByTestId("status").textContent).toBe("loading");
    await screen.findByText("anonymous");
  });

  it("logs in, fetches /me, becomes authenticated", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ data: { access_token: "tok", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
      http.get("/api/v1/me", () =>
        HttpResponse.json({
          data: {
            id: "u1", email: "a@b.com", username: "a", role: "user",
            tenantId: "t1", onboardingComplete: true, features: [],
          },
        }),
      ),
    );
    wrap();
    await screen.findByText("anonymous");
    await act(async () => { screen.getByText("login").click(); });
    await screen.findByText("authenticated");
    expect(screen.getByTestId("email").textContent).toBe("a@b.com");
  });
});
