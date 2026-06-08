import { z } from "zod";

const EnvSchema = z.object({
  VITE_API_BASE_URL: z.string().min(1, "VITE_API_BASE_URL is required"),
  VITE_WS_BASE_URL: z.string().optional().default(""),
  VITE_APP_NAME: z.string().min(1, "VITE_APP_NAME is required"),
  VITE_SENTRY_DSN: z.string().optional().default(""),
  VITE_ENABLE_DEVTOOLS: z
    .string()
    .optional()
    .default("false")
    .transform((s) => s === "true"),
});

const parsed = EnvSchema.safeParse(import.meta.env);

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
    .join("\n");
  throw new Error(
    `Frontend env validation failed.\n${issues}\n\nSet these in your .env file (see .env.example.frontend).`,
  );
}

export const env = {
  apiBaseUrl: parsed.data.VITE_API_BASE_URL,
  wsBaseUrl: parsed.data.VITE_WS_BASE_URL,
  appName: parsed.data.VITE_APP_NAME,
  sentryDsn: parsed.data.VITE_SENTRY_DSN,
  enableDevtools: parsed.data.VITE_ENABLE_DEVTOOLS,
} as const;

export type Env = typeof env;
