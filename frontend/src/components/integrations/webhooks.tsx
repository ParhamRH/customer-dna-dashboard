"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus, Send, Webhook } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { Integration } from "@/lib/types";
import { formatDateTime, relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, NativeSelect } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, SheetContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { TBody, THead, Table } from "@/components/ui/misc";
import { EmptyState, LoadingBlock, Panel } from "@/components/page";
import { Status, Tag } from "@/components/status";
import { CodeBlock } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

type Delivery = { job_id: string; event: string; status: string; attempts: number; max_attempts: number; status_code: number | null; error: string | null; created_at: string; finished_at: string | null };

const EVENT_COPY: Record<string, string> = {
  "asset.created": "An asset is uploaded or added",
  "asset.processed": "AI processing of an asset finishes",
  "review.decided": "Someone approves or rejects AI output",
  "knowledge.approved": "Brand knowledge is approved",
  "brand.version_published": "A brand version is published",
  "export.completed": "An export is ready",
  "import.committed": "An import is committed",
};

const VERIFY = `// Verify a delivery (Node.js). Header: x-bdna-signature: sha256=<hex>
import crypto from "node:crypto";
const ts = req.headers["x-bdna-timestamp"];
const expected = crypto.createHmac("sha256", process.env.BDNA_WEBHOOK_SECRET)
  .update(ts + "." + rawBody).digest("hex");
const ok = crypto.timingSafeEqual(Buffer.from("sha256=" + expected), Buffer.from(req.headers["x-bdna-signature"]));
// Also reject timestamps older than ~5 minutes to prevent replays.`;

export function WebhooksPanel({ items, eventTypes }: { items: Integration[]; eventTypes: string[] }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [edit, setEdit] = React.useState<Integration | "new" | null>(null);
  const [log, setLog] = React.useState<Integration | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ws.key("integrations") });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => ws.req(`/v1/integrations/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
  });
  const del = useMutation({ mutationFn: (id: string) => ws.req(`/v1/integrations/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const test = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/integrations/${id}/test`, { method: "POST" }),
    onSuccess: () => toast.success("Test event queued — check the delivery log in a few seconds"),
  });
  const brandName = (id: string | null) => (id ? (ws.brands.find((b) => b.id === id)?.name ?? "—") : "All brands");
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-base text-ink-2">
          Webhooks notify n8n or any HTTPS endpoint when something happens here. Each delivery is signed, retried with back-off, and carries only this workspace’s data.
        </p>
        <Button variant="primary" onClick={() => setEdit("new")}>
          <Plus /> New webhook
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState icon={<Webhook />} title="No webhooks">
          Add one to trigger an n8n workflow when assets are processed or knowledge is approved.
        </EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Name</th>
                <th>Endpoint</th>
                <th>Events</th>
                <th>Brand</th>
                <th>Last delivery</th>
                <th>Status</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {items.map((h) => {
                const c = h.config as { url?: string; events?: string[] };
                const ev = c.events ?? ["*"];
                return (
                  <tr key={h.id}>
                    <td className="font-medium">
                      {h.name}
                      {h.has_secret ? <div className="text-xs text-muted">Signed</div> : <div className="text-xs text-warning">Unsigned</div>}
                    </td>
                    <td className="max-w-[18rem] truncate font-mono text-[12px] text-ink-2" title={c.url}>
                      {c.url}
                    </td>
                    <td className="text-sm">{ev.includes("*") ? "All events" : ev.length === 1 ? ev[0] : `${ev.length} events`}</td>
                    <td className="text-sm">{brandName(h.brand_id)}</td>
                    <td className="whitespace-nowrap text-sm text-muted">{h.last_event_at ? relativeTime(h.last_event_at) : "Never"}</td>
                    <td>
                      <Status status={h.status === "active" ? "active" : "suspended"} label={h.status === "active" ? "Active" : "Disabled"} />
                    </td>
                    <td>
                      <div className="flex items-center gap-1">
                        <Button size="sm" disabled={h.status !== "active" || test.isPending} onClick={() => test.mutate(h.id)}>
                          <Send /> Test
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${h.name}`}>
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setLog(h)}>Delivery log</DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => setEdit(h)}>Edit</DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => patch.mutate({ id: h.id, body: { status: h.status === "active" ? "disabled" : "active" } })}>
                              {h.status === "active" ? "Disable" : "Enable"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-danger"
                              onSelect={async () => {
                                if (await confirm({ title: `Delete ${h.name}?`, description: "Pending deliveries are skipped.", confirmLabel: "Delete webhook", destructive: true })) del.mutate(h.id);
                              }}
                            >
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        </Panel>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-ink-2 hover:text-ink">How to verify signatures</summary>
        <div className="mt-3 grid gap-2">
          <p className="text-muted">
            Each request has <code className="font-mono text-[12px]">x-bdna-event</code>, <code className="font-mono text-[12px]">x-bdna-timestamp</code> and, when a secret is set, <code className="font-mono text-[12px]">x-bdna-signature</code> = HMAC-SHA256 of{" "}
            <code className="font-mono text-[12px]">{'timestamp + "." + body'}</code>.
          </p>
          <CodeBlock code={VERIFY} filename="verify.js" />
        </div>
      </details>
      <WebhookDialog target={edit} eventTypes={eventTypes} onClose={() => setEdit(null)} />
      <DeliveryLog hook={log} onClose={() => setLog(null)} />
    </div>
  );
}

function WebhookDialog({ target, eventTypes, onClose }: { target: Integration | "new" | null; eventTypes: string[]; onClose: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const existing = target && target !== "new" ? target : null;
  const [f, setF] = useResetState([existing?.id ?? target], () => {
    if (!existing) return { name: "", url: "", all: true, events: [] as string[], secret: "", brand_id: "" };
    const c = existing.config as { url?: string; events?: string[] };
    const ev = c.events ?? ["*"];
    return { name: existing.name, url: c.url ?? "", all: ev.includes("*"), events: ev.filter((e) => e !== "*"), secret: "", brand_id: existing.brand_id ?? "" };
  });
  const save = useMutation({
    mutationFn: () => {
      const config = { url: f.url, events: f.all ? ["*"] : f.events };
      const body: Record<string, unknown> = { name: f.name, config };
      if (f.secret) body.secret = f.secret;
      return existing
        ? ws.req(`/v1/integrations/${existing.id}`, { method: "PATCH", body })
        : ws.req("/v1/integrations", { method: "POST", body: { ...body, kind: "webhook", brand_id: f.brand_id || null } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("integrations") });
      toast.success(existing ? "Webhook saved" : "Webhook created");
      onClose();
    },
    onError: () => {},
  });
  const genSecret = () => {
    const a = new Uint8Array(24);
    crypto.getRandomValues(a);
    setF({ ...f, secret: Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("") });
  };
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="lg">
        <DialogHeader title={existing ? `Edit ${existing.name}` : "New webhook"} />
        <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" htmlFor="wh-name">
              <Input id="wh-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="n8n — asset sync" />
            </Field>
            <Field label="Brand" htmlFor="wh-brand" hint={existing ? "Fixed after creation" : undefined}>
              <NativeSelect id="wh-brand" value={f.brand_id} disabled={!!existing} onChange={(e) => setF({ ...f, brand_id: e.target.value })}>
                <option value="">All brands</option>
                {ws.brands.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <Field label="Endpoint URL" htmlFor="wh-url" hint="For n8n, use the production URL of a Webhook trigger node (method POST).">
            <Input id="wh-url" type="url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://n8n.example.com/webhook/brand-dna" className="font-mono text-[13px]" />
          </Field>
          <div className="grid gap-2">
            <Label>Events</Label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={f.all} onCheckedChange={(v) => setF({ ...f, all: !!v })} /> All events, including ones added later
            </label>
            {!f.all ? (
              <div className="grid gap-1.5 rounded-md border border-line p-3 sm:grid-cols-2">
                {eventTypes.map((e) => (
                  <label key={e} className="flex items-start gap-2 text-sm">
                    <Checkbox className="mt-0.5" checked={f.events.includes(e)} onCheckedChange={(v) => setF({ ...f, events: v ? [...f.events, e] : f.events.filter((x) => x !== e) })} />
                    <span>
                      <span className="font-mono text-[12px]">{e}</span>
                      <span className="block text-xs text-muted">{EVENT_COPY[e]}</span>
                    </span>
                  </label>
                ))}
              </div>
            ) : null}
          </div>
          <Field label="Signing secret" htmlFor="wh-secret" hint={existing?.has_secret ? "A secret is set. Leave empty to keep it, or enter a new one to rotate." : "Recommended. Stored encrypted; never shown again after saving."}>
            <div className="flex gap-2">
              <Input id="wh-secret" value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value })} className="font-mono text-[13px]" autoComplete="off" />
              <Button type="button" onClick={genSecret}>
                Generate
              </Button>
            </div>
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name.trim() || !f.url || (!f.all && !f.events.length) || save.isPending} onClick={() => save.mutate()}>
            {existing ? "Save webhook" : "Create webhook"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeliveryLog({ hook, onClose }: { hook: Integration | null; onClose: () => void }) {
  const ws = useWorkspace();
  const q = useQuery({
    queryKey: ws.key("webhook-deliveries", hook?.id),
    queryFn: () => ws.req<{ items: Delivery[] }>(`/v1/integrations/${hook!.id}/deliveries`),
    enabled: !!hook,
    refetchInterval: (query) => (query.state.data?.items.some((d) => d.status === "queued" || d.status === "running") ? 2000 : false),
  });
  return (
    <Dialog open={!!hook} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <DialogHeader title={hook ? `Deliveries — ${hook.name}` : ""} description="The 20 most recent delivery attempts. Failed deliveries are retried with back-off." />
        <div className="flex-1 overflow-y-auto p-5">
        {!q.data ? (
          <LoadingBlock rows={4} />
        ) : q.data.items.length === 0 ? (
          <p className="text-sm text-muted">No deliveries yet. Send a test event.</p>
        ) : (
          <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
            {q.data.items.map((d) => (
              <li key={d.job_id} className="rounded-md border border-line p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[12px]">{d.event}</span>
                  <Status status={d.status} />
                </div>
                <div className="mt-1 text-xs text-muted">
                  {formatDateTime(d.created_at)} · attempt {d.attempts} of {d.max_attempts}
                  {d.status_code ? ` · HTTP ${d.status_code}` : ""}
                </div>
                {d.error ? <p className="mt-1.5 break-words font-mono text-[11px] text-danger">{d.error}</p> : null}
                {d.status === "succeeded" && !d.status_code ? <Tag className="mt-1.5">Skipped</Tag> : null}
              </li>
            ))}
          </ul>
        )}
        </div>
      </SheetContent>
    </Dialog>
  );
}
