import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { server } from "../../../../tests/frontend/msw/server";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { AuthProvider } from "@/app/providers/AuthProvider";
import { LoginPage } from "./LoginPage";

function setup() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <QueryProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<div>home</div>} />
          </Routes>
        </AuthProvider>
      </QueryProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ error: { code: "AUTH_REFRESH_FAILED", message: "no" } }, { status: 401 }),
      ),
    );
  });

  it("renders the form", async () => {
    setup();
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("logs in and navigates home", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ data: { access_token: "tok", exp: Math.floor(Date.now() / 1000) + 3600 } }),
      ),
      http.get("/api/v1/me", () =>
        HttpResponse.json({
          data: { id: "u", email: "a@b.com", username: "a", role: "user", tenantId: "t", onboardingComplete: true, features: [] },
        }),
      ),
    );
    setup();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await screen.findByText("home");
  });
});
