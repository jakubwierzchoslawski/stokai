import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { RequireAuth } from "./RequireAuth";
import { RequireAdmin } from "./RequireAdmin";
import { OnboardingGate } from "./OnboardingGate";
import * as AuthMod from "../providers/AuthProvider";

const useAuthSpy = vi.spyOn(AuthMod, "useAuth");

function setAuth(state: AuthMod.AuthState) {
  useAuthSpy.mockReturnValue({
    state,
    login: vi.fn(), register: vi.fn(), logout: vi.fn(),
  });
}

describe("guards", () => {
  it("RequireAuth shows skeleton while loading", () => {
    setAuth({ status: "loading" });
    render(
      <MemoryRouter><RequireAuth><div>protected</div></RequireAuth></MemoryRouter>,
    );
    expect(screen.getByTestId("auth-loading")).toBeInTheDocument();
  });

  it("RequireAuth redirects anonymous to /login", () => {
    setAuth({ status: "anonymous" });
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/secret" element={<RequireAuth><div>secret</div></RequireAuth>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("RequireAdmin denies non-admin", () => {
    setAuth({
      status: "authenticated",
      user: { id: "u", email: "e", username: "u", role: "user", tenantId: "t", onboardingComplete: true, features: [] },
    });
    render(
      <MemoryRouter><RequireAdmin><div>admin only</div></RequireAdmin></MemoryRouter>,
    );
    expect(screen.getByTestId("access-denied")).toBeInTheDocument();
  });

  it("OnboardingGate redirects when onboarding incomplete", () => {
    setAuth({
      status: "authenticated",
      user: { id: "u", email: "e", username: "u", role: "user", tenantId: "t", onboardingComplete: false, features: [] },
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/onboarding" element={<div>onboarding</div>} />
          <Route element={<OnboardingGate />}>
            <Route path="/" element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("onboarding")).toBeInTheDocument();
  });
});
