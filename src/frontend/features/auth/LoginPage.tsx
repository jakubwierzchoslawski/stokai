import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/ui/button";
import { Card, CardContent, CardHeader } from "@/ui/card";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { LoginSchema, type LoginInput } from "./authSchemas";
import { ApiError, isAuthError } from "@/lib/api/errors";

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: { pathname: string } } | null)?.from?.pathname ?? ROUTES.home;

  const {
    register, handleSubmit, formState: { errors, isSubmitting }, setError,
  } = useForm<LoginInput>({ resolver: zodResolver(LoginSchema) });

  const onSubmit = async (values: LoginInput) => {
    try {
      await login(values.email, values.password);
      nav(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && isAuthError(err)) {
        setError("password", { message: err.message });
      } else {
        toast.error(err instanceof Error ? err.message : "Sign in failed");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-4">
      <Card className="w-full max-w-sm border-border bg-surface-1">
        <CardHeader>
          <div className="text-2xl font-semibold tracking-tight">StokAI</div>
          <div className="text-sm text-muted">Sign in to continue</div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" autoFocus {...register("email")} aria-invalid={!!errors.email} />
              {errors.email && <p className="text-xs text-negative">{errors.email.message}</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="current-password" {...register("password")} aria-invalid={!!errors.password} />
              {errors.password && <p className="text-xs text-negative">{errors.password.message}</p>}
            </div>
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
            <div className="flex items-center justify-between text-xs text-muted">
              <button type="button" className="hover:text-text" onClick={() => toast.info("Password reset is coming soon.")}>
                Forgot password?
              </button>
              <a href={ROUTES.register} className="hover:text-text">Create account</a>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
