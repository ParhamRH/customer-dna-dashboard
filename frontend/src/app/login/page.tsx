"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogIn } from "lucide-react";
import { request, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Wordmark } from "@/components/wordmark";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await request("/v1/auth/login", { method: "POST", body: { email, password } });
      qc.clear();
      const me = await request<Me>("/v1/auth/me");
      qc.setQueryData(["me"], me);
      const next = params.get("next");
      if (next && next.startsWith("/") && !next.startsWith("//")) router.replace(next);
      else if (me.user?.is_platform_admin) router.replace("/admin");
      else if (me.memberships?.length) router.replace(`/w/${me.memberships[0].slug}`);
      else router.replace("/no-access");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      <Field label="Work e-mail" htmlFor="email">
        <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
      </Field>
      <Field label="Password" htmlFor="password">
        <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      <Button type="submit" variant="primary" size="lg" disabled={busy || !email || !password} className="mt-1 justify-self-start">
        <LogIn /> {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh grid-rows-[auto_1fr_auto] px-6 py-8 sm:px-12">
      <Wordmark className="text-ink" />
      <div className="flex items-center">
        <div className="w-full max-w-sm">
          <h1 className="text-3xl font-semibold">Sign in</h1>
          <p className="mb-8 mt-2 text-md text-muted">Open the brand libraries you manage or belong to.</p>
          <React.Suspense>
            <LoginForm />
          </React.Suspense>
        </div>
      </div>
      <p className="max-w-md text-sm text-muted">
        Access is by invitation. Each customer library is isolated: you only see the workspaces you have been added to.
      </p>
    </main>
  );
}
