"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { AiDescribe, Integration } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Panel } from "@/components/page";
import { Status } from "@/components/status";
import { AiProviders } from "@/components/admin/ai";
import { useConfirm } from "@/components/confirm";

const CAPABILITIES: Record<string, string> = {
  vision: "Image & video interpretation",
  text: "Text & document analysis",
  embedding: "Text embeddings (semantic search)",
};
const PROVIDERS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  openai_compatible: "OpenAI-compatible endpoint",
  dev: "Development adapter (no external calls)",
};

export function AiOverridesPanel({ ai, overrides }: { ai: AiDescribe; overrides: Integration[] }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [open, setOpen] = React.useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ws.key("integrations") });
  const patch = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => ws.req(`/v1/integrations/${id}`, { method: "PATCH", body: { status } }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: string) => ws.req(`/v1/integrations/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-6">
      <div>
        <h3 className="mb-1 text-md font-semibold">In effect for this workspace</h3>
        <p className="mb-3 max-w-3xl text-sm text-muted">
          Platform defaults apply unless this workspace overrides a capability. Every AI result records the provider, model and prompt version that produced it, and is never official until a person approves it.
        </p>
        <AiProviders ai={ai} />
      </div>
      <div>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-md font-semibold">Workspace overrides</h3>
            <p className="text-sm text-muted">Use the customer’s own provider account or model, e.g. for data-residency or billing reasons.</p>
          </div>
          <Button onClick={() => setOpen(true)}>
            <Plus /> Add override
          </Button>
        </div>
        {overrides.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-strong px-4 py-6 text-center text-sm text-muted">No overrides — the platform defaults above are used.</p>
        ) : (
          <Panel>
            <Table>
              <THead>
                <tr>
                  <th>Name</th>
                  <th>Capability</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Key</th>
                  <th>Status</th>
                  <th className="w-0" />
                </tr>
              </THead>
              <TBody>
                {overrides.map((o) => {
                  const c = o.config as { capability?: string; provider?: string; model?: string; base_url?: string };
                  return (
                    <tr key={o.id}>
                      <td className="font-medium">{o.name}</td>
                      <td className="text-sm">{CAPABILITIES[c.capability ?? ""] ?? c.capability}</td>
                      <td className="text-sm">
                        {PROVIDERS[c.provider ?? ""] ?? c.provider}
                        {c.base_url ? <div className="font-mono text-[11px] text-muted">{c.base_url}</div> : null}
                      </td>
                      <td className="font-mono text-[12px]">{c.model ?? "provider default"}</td>
                      <td className="text-sm text-muted">{o.has_secret ? "Stored (encrypted)" : "None"}</td>
                      <td>
                        <Status status={o.status === "active" ? "active" : "suspended"} label={o.status === "active" ? "Active" : "Disabled"} />
                      </td>
                      <td>
                        <div className="flex gap-1">
                          <Button size="sm" onClick={() => patch.mutate({ id: o.id, status: o.status === "active" ? "disabled" : "active" })}>
                            {o.status === "active" ? "Disable" : "Enable"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={async () => {
                              if (await confirm({ title: `Remove ${o.name}?`, description: "The platform default takes over for this capability.", confirmLabel: "Remove override", destructive: true })) del.mutate(o.id);
                            }}
                          >
                            Remove
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </TBody>
            </Table>
          </Panel>
        )}
      </div>
      <OverrideDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

function OverrideDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open], () => ({ name: "", capability: "vision", provider: "anthropic", model: "", base_url: "", key: "" }));
  const save = useMutation({
    mutationFn: () =>
      ws.req("/v1/integrations", {
        method: "POST",
        body: {
          kind: "ai_provider",
          name: f.name || `${PROVIDERS[f.provider]} — ${CAPABILITIES[f.capability]}`,
          config: { capability: f.capability, provider: f.provider, ...(f.model ? { model: f.model } : {}), ...(f.base_url ? { base_url: f.base_url } : {}) },
          secret: f.key || null,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("integrations") });
      toast.success("Override added. New AI jobs use it; existing results keep their recorded provider.");
      onOpenChange(false);
    },
    onError: () => {},
  });
  const needsKey = f.provider !== "dev";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader title="AI provider override" description="Applies to this workspace only." />
        <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <Field label="Capability" htmlFor="ai-cap">
            <NativeSelect id="ai-cap" value={f.capability} onChange={(e) => setF({ ...f, capability: e.target.value })}>
              {Object.entries(CAPABILITIES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Provider" htmlFor="ai-prov">
            <NativeSelect id="ai-prov" value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })}>
              {Object.entries(PROVIDERS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {f.capability === "embedding" ? <p className="text-sm text-warning">Changing the embedding model requires re-indexing the brand before search results are comparable again.</p> : null}
          <Field label="Model" htmlFor="ai-model" hint="Leave empty for the provider’s default.">
            <Input id="ai-model" value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} className="font-mono text-[13px]" />
          </Field>
          {f.provider === "openai_compatible" ? (
            <Field label="Base URL" htmlFor="ai-base">
              <Input id="ai-base" type="url" value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder="https://llm.internal.example/v1" className="font-mono text-[13px]" />
            </Field>
          ) : null}
          {needsKey ? (
            <Field label="API key" htmlFor="ai-key" hint="Stored encrypted. It is never shown again or included in exports.">
              <Input id="ai-key" type="password" value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} autoComplete="off" />
            </Field>
          ) : null}
          <Field label="Name" htmlFor="ai-name" hint="Optional">
            <Input id="ai-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={(needsKey && !f.key) || (f.provider === "openai_compatible" && !f.base_url) || save.isPending} onClick={() => save.mutate()}>
            Add override
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
