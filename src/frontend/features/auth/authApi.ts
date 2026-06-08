import { z } from "zod";
import { api } from "../../lib/api/client";

const CurrentUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  username: z.string(),
  role: z.enum(["user", "admin"]),
  tenantId: z.string(),
  onboardingComplete: z.boolean(),
  features: z.array(z.string()),
});
export type CurrentUser = z.infer<typeof CurrentUserSchema>;

const TokenSchema = z.object({
  access_token: z.string(),
  exp: z.number(),
});

export async function postLogin(email: string, password: string) {
  const raw = await api<unknown>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
  return TokenSchema.parse(raw);
}

export async function postRegister(payload: { email: string; username: string; password: string }) {
  const raw = await api<unknown>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
  return TokenSchema.parse(raw);
}

export async function postLogout(): Promise<void> {
  await api("/auth/logout", { method: "POST" });
}

export async function fetchMe(): Promise<CurrentUser> {
  const raw = await api<unknown>("/me");
  return CurrentUserSchema.parse(raw);
}

export async function postRefresh() {
  const raw = await api<unknown>("/auth/refresh", { method: "POST", skipAuth: true });
  return TokenSchema.parse(raw);
}
