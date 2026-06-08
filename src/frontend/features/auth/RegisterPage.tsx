import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/ui/button";
import { Card, CardContent, CardHeader } from "@/ui/card";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { RegisterSchema, type RegisterInput } from "./authSchemas";
import { ApiError, isValidationError } from "@/lib/api/errors";

export function RegisterPage() {
  const { register: doRegister } = useAuth();
  const nav = useNavigate();
  const {
    register, handleSubmit, formState: { errors, isSubmitting }, setError, watch,
  } = useForm<RegisterInput>({ resolver: zodResolver(RegisterSchema) });
  const password = watch("password") ?? "";
  const strength = scoreStrength(password);

  const onSubmit = async (values: RegisterInput) => {
    try {
      await doRegister(values);
      nav(ROUTES.onboarding, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && isValidationError(err) && err.details?.["field"]) {
        const field = String(err.details["field"]) as keyof RegisterInput;
        setError(field, { message: err.message });
      } else {
        toast.error(err instanceof Error ? err.message : "Registration failed");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-4">
      <Card className="w-full max-w-sm border-border bg-surface-1">
        <CardHeader>
          <div className="text-2xl font-semibold tracking-tight">Create your account</div>
          <div className="text-sm text-muted">Join StokAI to access intelligence briefs.</div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" autoFocus {...register("email")} aria-invalid={!!errors.email} />
              {errors.email && <p className="text-xs text-negative">{errors.email.message}</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="username">Username</Label>
              <Input id="username" type="text" autoComplete="username" {...register("username")} aria-invalid={!!errors.username} />
              {errors.username && <p className="text-xs text-negative">{errors.username.message}</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="new-password" {...register("password")} aria-invalid={!!errors.password} />
              {errors.password && <p className="text-xs text-negative">{errors.password.message}</p>}
            </div>
            <PasswordStrength score={strength} />
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create account"}
            </Button>
            <div className="text-center text-xs text-muted">
              Already have an account? <a href={ROUTES.login} className="hover:text-text">Sign in</a>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function scoreStrength(p: string): 0 | 1 | 2 | 3 | 4 {
  let s = 0;
  if (p.length >= 8) s += 1;
  if (/[A-Z]/.test(p)) s += 1;
  if (/[0-9]/.test(p)) s += 1;
  if (/[^A-Za-z0-9]/.test(p)) s += 1;
  return Math.min(s, 4) as 0 | 1 | 2 | 3 | 4;
}

function PasswordStrength({ score }: { score: 0 | 1 | 2 | 3 | 4 }) {
  const colors = ["bg-surface-3", "bg-negative", "bg-warning", "bg-warning", "bg-positive"];
  const label = ["Too short", "Weak", "OK", "Good", "Strong"][score];
  return (
    <div className="space-y-1">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded ${i < score ? (colors[score] ?? "bg-surface-3") : "bg-surface-3"}`} />
        ))}
      </div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
