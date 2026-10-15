"use client";
import * as React from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { request, errorMessage } from "@/lib/api";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { CopyValue } from "@/components/code-block";

type Created = { organization_id: string; slug: string; brand_id: string | null; admin_user_id: string | null; admin_temporary_password: string | null };

function slugify(s: string) {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase()
    .slice(0, 80);
}

export function NewCustomerDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState({
    name: "",
    slug: "",
    industry: "",
    country: "",
    contact_name: "",
    contact_email: "",
    first_brand_name: "",
    admin_email: "",
    admin_name: "",
    quota_gb: "",
  });
  const [slugTouched, setSlugTouched] = React.useState(false);
  const [created, setCreated] = React.useState<Created | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  const create = useMutation({
    mutationFn: () =>
      request<Created>("/v1/organizations", {
        method: "POST",
        body: {
          name: f.name.trim(),
          slug: (slugTouched ? f.slug : slugify(f.name)) || undefined,
          industry: f.industry || undefined,
          country: f.country || undefined,
          contact_name: f.contact_name || undefined,
          contact_email: f.contact_email || undefined,
          first_brand_name: f.first_brand_name.trim() || f.name.trim(),
          admin_email: f.admin_email || undefined,
          admin_name: f.admin_name || undefined,
          storage_quota_bytes: f.quota_gb ? Math.round(parseFloat(f.quota_gb) * 1024 ** 3) : undefined,
        },
      }),
    onSuccess: (data) => {
      setCreated(data);
      qc.invalidateQueries({ queryKey: ["admin"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: () => {},
  });

  function reset(o: boolean) {
    if (!o) {
      setCreated(null);
      create.reset();
      setF({ name: "", slug: "", industry: "", country: "", contact_name: "", contact_email: "", first_brand_name: "", admin_email: "", admin_name: "", quota_gb: "" });
      setSlugTouched(false);
    }
    onOpenChange(o);
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent size="lg">
        <DialogHeader
          title={created ? "Customer created" : "New customer"}
          description={created ? undefined : "Creates an isolated workspace with its own brand library. Nothing is shared with other customers."}
        />
        {created ? (
          <>
            <DialogBody className="grid gap-4 text-base">
              <p>
                The workspace <span className="font-medium">{f.name}</span> is ready at{" "}
                <span className="font-mono text-sm">/w/{created.slug}</span>.
              </p>
              {created.admin_temporary_password ? (
                <div className="rounded-md border border-line bg-surface-2 p-3">
                  <p className="flex items-center gap-2 font-medium">
                    <KeyRound className="size-4" /> Temporary password for {f.admin_email}
                  </p>
                  <p className="mt-1 text-sm text-muted">
                    Shown once. Hand it over securely; the administrator should change it after signing in.
                  </p>
                  <CopyValue value={created.admin_temporary_password} className="mt-2 text-sm" />
                </div>
              ) : created.admin_user_id ? (
                <p className="text-muted">{f.admin_email} already had an account and was added as customer administrator.</p>
              ) : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="ghost" onClick={() => reset(false)}>
                Close
              </Button>
              <Button variant="primary" asChild>
                <Link href={`/w/${created.slug}`}>Open workspace</Link>
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            className="flex min-h-0 flex-1 flex-col"
          >
            <DialogBody className="grid gap-5">
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <legend className="mb-2 text-sm font-medium text-muted">Customer</legend>
                <Field label="Name" htmlFor="nc-name">
                  <Input id="nc-name" required value={f.name} onChange={set("name")} autoFocus />
                </Field>
                <Field label="Workspace address" htmlFor="nc-slug" hint="Used in links. Letters, numbers and dashes.">
                  <Input
                    id="nc-slug"
                    value={slugTouched ? f.slug : slugify(f.name)}
                    onChange={(e) => {
                      setSlugTouched(true);
                      setF((s) => ({ ...s, slug: slugify(e.target.value) }));
                    }}
                  />
                </Field>
                <Field label="Industry" htmlFor="nc-ind">
                  <Input id="nc-ind" value={f.industry} onChange={set("industry")} />
                </Field>
                <Field label="Country" htmlFor="nc-country">
                  <Input id="nc-country" value={f.country} onChange={set("country")} />
                </Field>
                <Field label="Contact name" htmlFor="nc-cn">
                  <Input id="nc-cn" value={f.contact_name} onChange={set("contact_name")} />
                </Field>
                <Field label="Contact e-mail" htmlFor="nc-ce">
                  <Input id="nc-ce" type="email" value={f.contact_email} onChange={set("contact_email")} />
                </Field>
              </fieldset>
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <legend className="mb-2 text-sm font-medium text-muted">Library</legend>
                <Field label="First brand" htmlFor="nc-brand" hint="Defaults to the customer name. More brands can be added later.">
                  <Input id="nc-brand" value={f.first_brand_name} onChange={set("first_brand_name")} placeholder={f.name} />
                </Field>
                <Field label="Storage quota (GB)" htmlFor="nc-quota" hint="Leave empty for no limit.">
                  <Input id="nc-quota" type="number" min="0" step="0.5" value={f.quota_gb} onChange={set("quota_gb")} />
                </Field>
              </fieldset>
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <legend className="mb-2 text-sm font-medium text-muted">Customer administrator (optional)</legend>
                <Field label="E-mail" htmlFor="nc-ae" hint="Receives a temporary password if they have no account yet.">
                  <Input id="nc-ae" type="email" value={f.admin_email} onChange={set("admin_email")} />
                </Field>
                <Field label="Full name" htmlFor="nc-an">
                  <Input id="nc-an" value={f.admin_name} onChange={set("admin_name")} />
                </Field>
              </fieldset>
              {create.error ? (
                <p role="alert" className="text-sm text-danger">
                  {errorMessage(create.error)}
                </p>
              ) : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="ghost" onClick={() => reset(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={!f.name.trim() || create.isPending}>
                {create.isPending ? "Creating…" : "Create customer"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
