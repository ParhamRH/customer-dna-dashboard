"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { PromptTemplate } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { LoadingBlock, Panel } from "@/components/page";
import { Tag } from "@/components/status";
import { CodeBlock } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

export function PromptsPanel({ canEdit }: { canEdit: boolean }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: ws.key("prompts"), queryFn: () => ws.req<{ items: PromptTemplate[]; keys: string[] }>("/v1/prompts") });
  const [view, setView] = React.useState<PromptTemplate | null>(null);
  const [edit, setEdit] = React.useState<PromptTemplate | null>(null);
  const reset = useMutation({
    mutationFn: (key: string) => ws.req(`/v1/prompts/${key}/reset`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("prompts") });
      toast.success("Back to the platform default");
    },
  });
  if (!q.data) return <LoadingBlock rows={4} />;
  const rows = q.data.keys.map((key) => {
    const versions = q.data.items.filter((p) => p.key === key);
    const own = versions.filter((p) => p.organization_id);
    const active = own.find((p) => p.is_active) ?? versions.find((p) => !p.organization_id && p.is_active) ?? versions[0];
    return { key, active, versions, own };
  });
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <p className="max-w-3xl text-base text-ink-2">
        The instructions sent to AI models when assets are analysed and briefs are generated. A customised version applies to this workspace only, and every analysis records which version produced it.
      </p>
      <Panel>
        <ul className="divide-y divide-line">
          {rows.map(({ key, active, own }) =>
            active ? (
              <li key={key} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{active.name}</span>
                    {active.organization_id ? <Tag tone="accent">Customised · v{active.version}</Tag> : <Tag>Platform default · v{active.version}</Tag>}
                  </div>
                  <div className="text-sm text-muted">
                    <span className="font-mono text-[12px]">{key}</span> · {active.purpose}
                    {own.length ? ` · ${own.length} customised version${own.length === 1 ? "" : "s"}, latest ${formatDate(own[0].created_at)}` : ""}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => setView(active)}>
                    View
                  </Button>
                  {canEdit ? (
                    <Button size="sm" onClick={() => setEdit(active)}>
                      Customise
                    </Button>
                  ) : null}
                  {canEdit && active.organization_id ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        if (await confirm({ title: "Use the platform default?", description: "Your customised versions are kept for provenance but stop being used for new jobs.", confirmLabel: "Use default" })) reset.mutate(key);
                      }}
                    >
                      Use default
                    </Button>
                  ) : null}
                </div>
              </li>
            ) : null,
          )}
        </ul>
      </Panel>
      <Dialog open={!!view} onOpenChange={(o) => !o && setView(null)}>
        <DialogContent size="xl">
          <DialogHeader title={view ? `${view.name} — v${view.version}` : ""} description={view?.organization_id ? "Customised for this workspace" : "Platform default"} />
          <DialogBody>{view ? <CodeBlock code={view.template} filename={`${view.key}.v${view.version}.txt`} maxHeight="60vh" /> : null}</DialogBody>
        </DialogContent>
      </Dialog>
      <EditPrompt base={edit} onClose={() => setEdit(null)} />
    </div>
  );
}

function EditPrompt({ base, onClose }: { base: PromptTemplate | null; onClose: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [text, setText] = useResetState([base?.id], () => base?.template ?? "");
  const save = useMutation({
    mutationFn: () => ws.req<PromptTemplate>("/v1/prompts", { method: "POST", body: { key: base!.key, template: text } }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ws.key("prompts") });
      toast.success(`Saved as version ${p.version}. New AI jobs use it.`);
      onClose();
    },
    onError: () => {},
  });
  // Templates use $name placeholders (Python string.Template), filled in by the platform at run time.
  const placeholders = Array.from(new Set((base?.template ?? "").match(/\$[a-z_]+\b/g) ?? []));
  const missing = placeholders.filter((p) => !text.includes(p));
  return (
    <Dialog open={!!base} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="xl">
        <DialogHeader title={base ? `Customise ${base.name}` : ""} description="Saving creates a new version for this workspace. Existing analyses keep the version they were made with." />
        <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={18} className="font-mono text-[12px] leading-relaxed" aria-label="Prompt template" />
          {placeholders.length ? (
            <p className="text-sm text-muted">
              Placeholders filled in by the platform: {placeholders.map((p) => <code key={p} className="mr-1.5 font-mono text-[12px]">{p}</code>)}
            </p>
          ) : null}
          {missing.length ? <p className="text-sm text-warning">Missing placeholders: {missing.join(", ")} — the model will not receive that information.</p> : null}
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={text.trim().length < 20 || text === base?.template || save.isPending} onClick={() => save.mutate()}>
            Save new version
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
