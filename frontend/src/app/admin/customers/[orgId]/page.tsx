"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowLeft, ExternalLink, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { request, errorMessage } from "@/lib/api";
import type { ActivityItem, CustomerRow, Organization } from "@/lib/types";
import { formatBytes, formatDate, formatNumber } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, Figure, LoadingBlock, PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Status } from "@/components/status";
import { MembersManager } from "@/components/manage/members";
import { ExportsPanel } from "@/components/manage/exports";
import { ActivityFeed } from "@/components/activity";
import { useConfirm } from "@/components/confirm";
import { DnaStrip } from "@/components/dna-strip";

type OrgDetail = Organization & { stats: Partial<CustomerRow> };

export default function CustomerDetail() {
  const { orgId } = useParams<{ orgId: string }>();
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: ["admin", "customer", orgId], queryFn: () => request<OrgDetail>(`/v1/organizations/${orgId}`) });
  const activity = useQuery({
    queryKey: ["admin", "activity", "org", orgId],
    queryFn: () => request<{ items: ActivityItem[] }>("/v1/platform/activity", { params: { organization_id: orgId, limit: 60 } }),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const lifecycle = useMutation({
    mutationFn: ({ action, body }: { action: "archive" | "reactivate" | "request-deletion"; body?: unknown }) =>
      request<{ status: string; purge_at?: string }>(`/v1/organizations/${orgId}/${action}`, { method: "POST", body }),
    onSuccess: (r) => {
      refresh();
      toast.success(r.purge_at ? `Scheduled for permanent deletion on ${formatDate(r.purge_at)}` : `Customer is now ${r.status}`);
    },
  });

  if (q.error) return <Main><ErrorState error={q.error} onRetry={() => q.refetch()} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={6} /></Main>;
  const o = q.data;
  const s = o.stats;

  return (
    <Main wide>
      <Link href="/admin/customers" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-3.5" /> Customers
      </Link>
      <PageHeader
        title={o.name}
        meta={
          <>
            <Status status={o.status} />
            <span className="font-mono text-xs">/w/{o.slug}</span>
            <span>Customer since {formatDate(o.created_at)}</span>
            {o.deletion_requested_at ? <span className="text-danger">Deletion requested {formatDate(o.deletion_requested_at)}</span> : null}
          </>
        }
        actions={
          <>
            {o.status === "active" ? (
              <Button
                variant="secondary"
                onClick={async () => {
                  if (
                    await confirm({
                      title: `Archive ${o.name}?`,
                      description: "Customer users lose access immediately. Data is kept and platform administrators can still open the workspace. You can reactivate at any time.",
                      confirmLabel: "Archive customer",
                    })
                  )
                    lifecycle.mutate({ action: "archive" });
                }}
              >
                <Archive /> Archive
              </Button>
            ) : (
              <Button variant="secondary" onClick={() => lifecycle.mutate({ action: "reactivate" })}>
                <RotateCcw /> Reactivate
              </Button>
            )}
            {o.status !== "pending_deletion" ? (
              <>
                <Button
                  variant="danger-outline"
                  onClick={async () => {
                    if (
                      await confirm({
                        title: "Schedule permanent deletion",
                        description: (
                          <span>
                            The workspace is locked now and every record and file of <b>{o.name}</b> is permanently deleted after a 30-day grace
                            period. Reactivating before then cancels the deletion. Export the library first if the customer needs a copy.
                          </span>
                        ),
                        confirmLabel: "Schedule deletion",
                        destructive: true,
                        typeToConfirm: o.slug,
                      })
                    )
                      lifecycle.mutate({ action: "request-deletion", body: { confirm_slug: o.slug, grace_days: 30 } });
                  }}
                >
                  <Trash2 /> Delete…
                </Button>
                <Button variant="primary" onClick={() => router.push(`/w/${o.slug}`)}>
                  Open workspace <ExternalLink />
                </Button>
              </>
            ) : null}
          </>
        }
      />
      <DnaStrip colors={(s.palette ?? []).map((p) => ({ hex: p.hex, name: p.name, weight: p.role === "primary" ? 3 : 1 }))} height={6} interactive className="mb-6 max-w-xl" label={o.name} />
      <Panel className="mb-8 grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-6">
        <Figure label="Brands" value={formatNumber(s.brand_count ?? 0)} />
        <Figure label="Members" value={formatNumber(s.member_count ?? 0)} />
        <Figure label="Assets" value={formatNumber(s.asset_count ?? 0)} />
        <Figure label="Storage" value={formatBytes(s.storage_bytes ?? 0)} hint={o.storage_quota_bytes ? `of ${formatBytes(o.storage_quota_bytes)} quota` : "No quota"} />
        <Figure label="Awaiting review" value={formatNumber(s.pending_reviews ?? 0)} />
        <Figure label="Retention after archive" value={o.retention_days_after_archive ? `${o.retention_days_after_archive} d` : "—"} />
      </Panel>
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="members">Users & roles</TabsTrigger>
          <TabsTrigger value="exports">Exports</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>
        <TabsContent value="profile">
          <ProfileForm org={o} onSaved={refresh} />
        </TabsContent>
        <TabsContent value="members">
          <MembersManager org={o.id} canManage={o.status !== "pending_deletion"} />
        </TabsContent>
        <TabsContent value="exports">
          <ExportsPanel org={o.id} canCreate={o.status !== "pending_deletion"} />
        </TabsContent>
        <TabsContent value="activity">
          {activity.data ? <ActivityFeed items={activity.data.items} showCustomer={false} /> : <LoadingBlock rows={6} />}
        </TabsContent>
      </Tabs>
    </Main>
  );
}

function ProfileForm({ org, onSaved }: { org: Organization; onSaved: () => void }) {
  const [f, setF] = React.useState({
    name: org.name,
    legal_name: org.legal_name ?? "",
    contact_name: org.contact_name ?? "",
    contact_email: org.contact_email ?? "",
    website: org.website ?? "",
    industry: org.industry ?? "",
    country: org.country ?? "",
    notes: org.notes ?? "",
    quota_gb: org.storage_quota_bytes ? String(+(org.storage_quota_bytes / 1024 ** 3).toFixed(2)) : "",
    retention: org.retention_days_after_archive ? String(org.retention_days_after_archive) : "",
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF((s) => ({ ...s, [k]: e.target.value }));
  const save = useMutation({
    mutationFn: () =>
      request(`/v1/organizations/${org.id}`, {
        method: "PATCH",
        body: {
          name: f.name,
          legal_name: f.legal_name || null,
          contact_name: f.contact_name || null,
          contact_email: f.contact_email || null,
          website: f.website || null,
          industry: f.industry || null,
          country: f.country || null,
          notes: f.notes || null,
          storage_quota_bytes: f.quota_gb ? Math.round(parseFloat(f.quota_gb) * 1024 ** 3) : null,
          retention_days_after_archive: f.retention ? parseInt(f.retention, 10) : null,
        },
      }),
    onSuccess: () => {
      onSaved();
      toast.success("Customer profile saved");
    },
    onError: () => {},
  });
  return (
    <form
      className="grid max-w-3xl gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Name" htmlFor="p-name">
        <Input id="p-name" required value={f.name} onChange={set("name")} />
      </Field>
      <Field label="Legal name" htmlFor="p-legal">
        <Input id="p-legal" value={f.legal_name} onChange={set("legal_name")} />
      </Field>
      <Field label="Contact name" htmlFor="p-cn">
        <Input id="p-cn" value={f.contact_name} onChange={set("contact_name")} />
      </Field>
      <Field label="Contact e-mail" htmlFor="p-ce">
        <Input id="p-ce" type="email" value={f.contact_email} onChange={set("contact_email")} />
      </Field>
      <Field label="Website" htmlFor="p-web">
        <Input id="p-web" value={f.website} onChange={set("website")} />
      </Field>
      <Field label="Industry" htmlFor="p-ind">
        <Input id="p-ind" value={f.industry} onChange={set("industry")} />
      </Field>
      <Field label="Country" htmlFor="p-country">
        <Input id="p-country" value={f.country} onChange={set("country")} />
      </Field>
      <Field label="Storage quota (GB)" htmlFor="p-quota" hint="Uploads beyond the quota are refused. Empty means unlimited.">
        <Input id="p-quota" type="number" min="0" step="0.5" value={f.quota_gb} onChange={set("quota_gb")} />
      </Field>
      <Field label="Retention after archive (days)" htmlFor="p-ret" hint="Agreed retention period for an archived customer's data.">
        <Input id="p-ret" type="number" min="0" max="3650" value={f.retention} onChange={set("retention")} />
      </Field>
      <Field label="Internal notes" htmlFor="p-notes" className="sm:col-span-2">
        <Textarea id="p-notes" value={f.notes} onChange={set("notes")} rows={3} />
      </Field>
      {save.error ? <p className="text-sm text-danger sm:col-span-2">{errorMessage(save.error)}</p> : null}
      <div className="sm:col-span-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save profile"}
        </Button>
      </div>
    </form>
  );
}
