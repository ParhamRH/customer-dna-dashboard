"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { Organization } from "@/lib/types";
import { Main } from "@/components/shell";
import { MetaList, PageHeader, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MembersManager } from "@/components/manage/members";
import { BrandsPanel } from "@/components/settings/brands";
import { AuditPanel, JobsPanel } from "@/components/settings/audit-jobs";
import { formatBytes, formatDate } from "@/lib/utils";

function isFull(o: unknown): o is Organization {
  return !!o && typeof o === "object" && "created_at" in o;
}

function ProfileForm({ org, canEdit }: { org: Organization; canEdit: boolean }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const init = React.useCallback(
    () => ({ name: org.name, legal_name: org.legal_name ?? "", contact_name: org.contact_name ?? "", contact_email: org.contact_email ?? "", website: org.website ?? "", industry: org.industry ?? "", country: org.country ?? "", notes: org.notes ?? "" }),
    [org],
  );
  // Re-initialise when the saved profile changes (after saving or a refetch).
  const [f, setF] = useResetState([org.updated_at], init);
  const dirty = JSON.stringify(f) !== JSON.stringify(init());
  const save = useMutation({
    mutationFn: () => ws.req<Organization>("/v1/workspace", { method: "PATCH", body: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, k === "name" ? v : v || null])) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("workspace") });
      toast.success("Workspace profile saved");
    },
    onError: () => {},
  });
  const field = (k: keyof typeof f, label: string, props: React.ComponentProps<typeof Input> = {}) => (
    <Field label={label} htmlFor={`org-${k}`}>
      <Input id={`org-${k}`} value={f[k]} disabled={!canEdit} onChange={(e) => setF({ ...f, [k]: e.target.value })} {...props} />
    </Field>
  );
  return (
    <div className="grid max-w-3xl gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {field("name", "Workspace name")}
        {field("legal_name", "Legal name")}
        {field("contact_name", "Contact person")}
        {field("contact_email", "Contact email", { type: "email" })}
        {field("website", "Website", { type: "url", placeholder: "https://" })}
        {field("industry", "Industry")}
        {field("country", "Country")}
      </div>
      <Field label="Notes" htmlFor="org-notes">
        <Textarea id="org-notes" rows={3} value={f.notes} disabled={!canEdit} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      </Field>
      {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
      {canEdit ? (
        <div className="flex gap-2">
          <Button variant="primary" disabled={!dirty || !f.name.trim() || save.isPending} onClick={() => save.mutate()}>
            Save profile
          </Button>
          {dirty ? (
            <Button variant="ghost" onClick={() => setF(init())}>
              Discard changes
            </Button>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-muted">Only workspace administrators can change the profile.</p>
      )}
    </div>
  );
}

const TABS = ["profile", "brands", "members", "audit", "jobs"] as const;

export default function SettingsPage() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const visible = TABS.filter((t) => (t === "members" ? ws.can("users.read") : t === "audit" ? ws.can("audit.read") : t === "jobs" ? ws.can("jobs.read") : true));
  const tab = (visible as readonly string[]).includes(params.get("tab") ?? "") ? params.get("tab")! : "profile";
  const org = ws.org;
  return (
    <Main>
      <PageHeader title="Settings" description="The workspace profile, its brands, who has access, and what has happened." />
      <Tabs value={tab} onValueChange={(t) => router.replace(`${pathname}?tab=${t}`, { scroll: false })}>
        <TabsList>
          <TabsTrigger value="profile">Workspace</TabsTrigger>
          <TabsTrigger value="brands">Brands · {ws.brands.length}</TabsTrigger>
          {visible.includes("members") ? <TabsTrigger value="members">Members</TabsTrigger> : null}
          {visible.includes("audit") ? <TabsTrigger value="audit">Audit log</TabsTrigger> : null}
          {visible.includes("jobs") ? <TabsTrigger value="jobs">Processing jobs</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="profile">
          {isFull(org) ? (
            <>
              <Section>
                <ProfileForm org={org} canEdit={ws.can("org.manage")} />
              </Section>
              <Section title="Account">
                <MetaList
                  items={[
                    ["Workspace ID", <span key="id" className="font-mono text-[12px]">{org.id}</span>],
                    ["Address", <span key="s" className="font-mono text-[12px]">/w/{org.slug}</span>],
                    ["Created", formatDate(org.created_at)],
                    ["Storage quota", org.storage_quota_bytes ? formatBytes(org.storage_quota_bytes) : "Not limited"],
                    ["Retention after archiving", org.retention_days_after_archive ? `${org.retention_days_after_archive} days` : "Platform default"],
                  ]}
                />
                <p className="mt-3 text-sm text-muted">Quotas, archiving and deletion are managed by the platform administrator.</p>
              </Section>
            </>
          ) : (
            <p className="text-sm text-muted">You can see this workspace’s name only.</p>
          )}
        </TabsContent>
        <TabsContent value="brands">
          <BrandsPanel />
        </TabsContent>
        {visible.includes("members") ? (
          <TabsContent value="members">
            <MembersManager org={ws.orgId} canManage={ws.can("users.manage")} />
          </TabsContent>
        ) : null}
        {visible.includes("audit") ? (
          <TabsContent value="audit">
            <AuditPanel />
          </TabsContent>
        ) : null}
        {visible.includes("jobs") ? (
          <TabsContent value="jobs">
            <JobsPanel />
          </TabsContent>
        ) : null}
      </Tabs>
    </Main>
  );
}
