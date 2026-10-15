"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { ApiTokenRow } from "@/lib/types";
import { ORG_ROLES, ROLE_LABELS, ROLE_SUMMARY } from "@/lib/labels";
import { formatDate, relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { TBody, THead, Table } from "@/components/ui/misc";
import { EmptyState, ErrorState, LoadingBlock, Panel } from "@/components/page";
import { Status } from "@/components/status";
import { CodeBlock } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

const ROLE_RANK: Record<string, number> = { viewer: 1, reviewer: 2, editor: 3, creative_director: 4, customer_admin: 5, platform_super_admin: 9 };

function tokenState(t: ApiTokenRow): { status: string; label: string } {
  if (t.revoked_at) return { status: "rejected", label: "Revoked" };
  if (t.expires_at && new Date(t.expires_at) < new Date()) return { status: "expired", label: "Expired" };
  return { status: "active", label: "Active" };
}

export function TokensPanel({ mcpUrl, open, setOpen }: { mcpUrl?: string; open: boolean; setOpen: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [created, setCreated] = React.useState<ApiTokenRow | null>(null);
  const q = useQuery({ queryKey: ws.key("api-tokens"), queryFn: () => ws.req<{ items: ApiTokenRow[] }>("/v1/workspace/api-tokens") });
  const revoke = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/workspace/api-tokens/${id}/revoke`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("api-tokens") });
      toast.success("Token revoked. Clients using it lose access immediately.");
    },
  });
  const brandName = (id: string | null) => (id ? (ws.brands.find((b) => b.id === id)?.name ?? "Unknown brand") : "All brands");
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-base text-ink-2">
          Tokens let scripts, n8n and AI clients (over MCP) use this workspace’s API. A token is bound to this workspace — optionally to one brand — and can never do more than its role allows.
        </p>
        <Button variant="primary" onClick={() => setOpen(true)}>
          <Plus /> New token
        </Button>
      </div>
      {q.error ? <ErrorState error={q.error} /> : null}
      {!q.data ? (
        <LoadingBlock rows={3} />
      ) : q.data.items.length === 0 ? (
        <EmptyState icon={<KeyRound />} title="No tokens yet">
          Create a viewer token to connect an AI assistant over MCP.
        </EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Name</th>
                <th>Token</th>
                <th>Role</th>
                <th>Scope</th>
                <th>Last used</th>
                <th>Expires</th>
                <th>Status</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((t) => {
                const st = tokenState(t);
                return (
                  <tr key={t.id}>
                    <td className="font-medium">{t.name}</td>
                    <td className="font-mono text-[12px] text-muted">{t.token_prefix}…</td>
                    <td className="text-sm">{ROLE_LABELS[t.role] ?? t.role}</td>
                    <td className="text-sm">
                      {brandName(t.brand_id)}
                      {t.scopes.length ? <div className="text-xs text-muted">{t.scopes.length} scopes</div> : null}
                    </td>
                    <td className="whitespace-nowrap text-sm text-muted">{t.last_used_at ? relativeTime(t.last_used_at) : "Never"}</td>
                    <td className="whitespace-nowrap text-sm text-muted">{t.expires_at ? formatDate(t.expires_at) : "Never"}</td>
                    <td>
                      <Status status={st.status} label={st.label} />
                    </td>
                    <td>
                      {st.label === "Active" ? (
                        <Button
                          size="sm"
                          variant="danger-outline"
                          onClick={async () => {
                            if (await confirm({ title: `Revoke ${t.name}?`, description: "Anything using this token stops working immediately. This cannot be undone.", confirmLabel: "Revoke token", destructive: true }))
                              revoke.mutate(t.id);
                          }}
                        >
                          Revoke
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        </Panel>
      )}
      <NewTokenDialog open={open} onOpenChange={setOpen} onCreated={setCreated} />
      <Dialog open={!!created} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent size="lg">
          <DialogHeader title="Copy your token now" description="This is the only time the full token is shown. Store it in your secret manager; the platform keeps only a hash." />
          <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
            {created?.token ? <CodeBlock code={created.token} label="API token" /> : null}
            {created?.token && mcpUrl ? (
              <CodeBlock
                label="MCP client configuration (Streamable HTTP)"
                code={JSON.stringify({ mcpServers: { "brand-dna": { type: "http", url: mcpUrl, headers: { Authorization: `Bearer ${created.token}` } } } }, null, 2)}
                mime="application/json"
              />
            ) : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="primary" onClick={() => setCreated(null)}>
              I’ve stored it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NewTokenDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (t: ApiTokenRow) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open], () => ({ name: "", role: "viewer", brand_id: "", expires: "90" }));
  const mine = ROLE_RANK[ws.role] ?? 0;
  const roles = ORG_ROLES.filter((r) => (ROLE_RANK[r] ?? 0) <= mine);
  const create = useMutation({
    mutationFn: () =>
      ws.req<ApiTokenRow>("/v1/workspace/api-tokens", {
        method: "POST",
        body: { name: f.name, role: f.role, brand_id: f.brand_id || null, expires_in_days: f.expires ? Number(f.expires) : null },
      }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ws.key("api-tokens") });
      onOpenChange(false);
      onCreated(t);
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader title="New API token" description="Give each client its own token so you can revoke one without affecting the others." />
        <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <Field label="Name" htmlFor="tk-name" hint="Where it is used, e.g. “Claude Desktop — Anna” or “n8n asset sync”.">
            <Input id="tk-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus />
          </Field>
          <Field label="Role" htmlFor="tk-role" hint={ROLE_SUMMARY[f.role]}>
            <NativeSelect id="tk-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                  {r === "viewer" ? " — recommended for AI clients" : ""}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Brand" htmlFor="tk-brand">
            <NativeSelect id="tk-brand" value={f.brand_id} onChange={(e) => setF({ ...f, brand_id: e.target.value })}>
              <option value="">All brands in this workspace</option>
              {ws.brands.map((b) => (
                <option key={b.id} value={b.id}>
                  Only {b.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Expires" htmlFor="tk-exp">
            <NativeSelect id="tk-exp" value={f.expires} onChange={(e) => setF({ ...f, expires: e.target.value })}>
              <option value="30">In 30 days</option>
              <option value="90">In 90 days</option>
              <option value="365">In a year</option>
              <option value="">Never</option>
            </NativeSelect>
          </Field>
          {create.error ? <p className="text-sm text-danger">{errorMessage(create.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name.trim() || create.isPending} onClick={() => create.mutate()}>
            Create token
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
