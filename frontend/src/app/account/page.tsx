"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { request, errorMessage } from "@/lib/api";
import { useAuthRedirect, useMe } from "@/lib/session";
import { ROLE_LABELS } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { MetaList, PageHeader, Section } from "@/components/page";
import { Wordmark } from "@/components/wordmark";

export default function AccountPage() {
  useAuthRedirect();
  const me = useMe();
  const router = useRouter();
  const [cur, setCur] = React.useState("");
  const [next, setNext] = React.useState("");
  const [again, setAgain] = React.useState("");
  const change = useMutation({
    mutationFn: () => request("/v1/auth/password", { method: "POST", body: { current_password: cur, new_password: next } }),
    onSuccess: () => {
      toast.success("Password changed");
      setCur("");
      setNext("");
      setAgain("");
    },
    onError: () => {},
  });
  const mismatch = again.length > 0 && next !== again;
  return (
    <main className="mx-auto max-w-2xl px-6 py-8">
      <div className="mb-8 flex items-center justify-between">
        <Wordmark />
        <Button variant="ghost" onClick={() => router.back()}>
          <ArrowLeft /> Back
        </Button>
      </div>
      <PageHeader title="Your account" />
      <Section title="Profile">
        <MetaList
          items={[
            ["Name", me.data?.user?.full_name],
            ["E-mail", me.data?.user?.email],
            ["Platform administrator", me.data?.user?.is_platform_admin ? "Yes" : "No"],
            [
              "Workspaces",
              me.data?.memberships?.length
                ? me.data.memberships.map((m) => `${m.name} (${ROLE_LABELS[m.role] ?? m.role})`).join(", ")
                : "None",
            ],
          ]}
        />
      </Section>
      <Section title="Change password" description="At least 10 characters. Other sessions stay signed in.">
        <form
          className="grid max-w-sm gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate();
          }}
        >
          <Field label="Current password" htmlFor="pw-cur">
            <Input id="pw-cur" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
          </Field>
          <Field label="New password" htmlFor="pw-new">
            <Input id="pw-new" type="password" autoComplete="new-password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Repeat new password" htmlFor="pw-again" error={mismatch ? "The passwords do not match" : undefined}>
            <Input id="pw-again" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} aria-invalid={mismatch} />
          </Field>
          {change.error ? <p className="text-sm text-danger">{errorMessage(change.error)}</p> : null}
          <Button type="submit" variant="primary" className="justify-self-start" disabled={!cur || next.length < 10 || next !== again || change.isPending}>
            Change password
          </Button>
        </form>
      </Section>
    </main>
  );
}
