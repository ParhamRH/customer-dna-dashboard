"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useDesignTokens } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { DesignToken } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Segmented } from "@/components/ui/tabs";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Panel, Section } from "@/components/page";
import { CodeBlock } from "@/components/code-block";
import { Status } from "@/components/status";
import { StatusSelect } from "./status-select";

const TOKEN_TYPES = ["color", "dimension", "fontFamily", "fontWeight", "duration", "cubicBezier", "number", "shadow", "border", "typography", "gradient", "strokeStyle", "transition"];

function displayValue(v: unknown): string {
  return typeof v === "string" ? v : JSON.stringify(v);
}

function parseValue(s: string): unknown {
  const t = s.trim();
  if (!t) return "";
  if (/^[[{"\d-]/.test(t)) {
    try {
      return JSON.parse(t);
    } catch {
      return t;
    }
  }
  return t;
}

function TokenPreview({ t }: { t: DesignToken }) {
  const v = t.value;
  if (t.token_type === "color" && typeof v === "string") return <span className="inline-block size-4 rounded-sm border border-line" style={{ background: v }} />;
  if (t.token_type === "dimension" && typeof v === "string" && /px|rem/.test(v))
    return <span className="inline-block h-2 rounded-sm bg-ink-2" style={{ width: `min(${v}, 120px)` }} />;
  if (t.token_type === "cubicBezier" && Array.isArray(v) && v.length === 4) {
    const [x1, y1, x2, y2] = v as number[];
    return (
      <svg viewBox="0 0 20 20" className="size-5 text-ink-2" aria-hidden>
        <path d={`M1 19 C ${1 + x1 * 18} ${19 - y1 * 18}, ${1 + x2 * 18} ${19 - y2 * 18}, 19 1`} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  }
  return null;
}

function TokenDialog({ token, domain, open, onOpenChange }: { token: DesignToken | null; domain: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open, token?.id], () =>
    token
      ? { path: token.path, token_type: token.token_type, value: displayValue(token.value), description: token.description ?? "", category: token.category, status: token.status }
      : { path: "", token_type: "dimension", value: "", description: "", category: "", status: "draft" },
  );
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, value: parseValue(f.value), description: f.description || null, category: f.category || f.path.split(".")[0], domain_key: domain };
      return token
        ? ws.req(`/v1/design-tokens/${token.id}`, { method: "PATCH", body })
        : ws.req(`/v1/brands/${ws.brand.id}/design-tokens`, { method: "POST", body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("tokens") });
      toast.success(token ? "Token updated" : "Token created");
      onOpenChange(false);
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader title={token ? "Edit token" : "New design token"} description="W3C Design Tokens format. The path becomes the CSS variable name (spacing.4 → --spacing-4)." />
        <DialogBody className="grid gap-3">
          <Field label="Path" htmlFor="t-path" hint="Dot-separated, e.g. spacing.4 or motion.duration.base">
            <Input id="t-path" className="font-mono text-sm" value={f.path} onChange={(e) => setF({ ...f, path: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type" htmlFor="t-type">
              <NativeSelect id="t-type" value={f.token_type} onChange={(e) => setF({ ...f, token_type: e.target.value })}>
                {TOKEN_TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Category" htmlFor="t-cat">
              <Input id="t-cat" value={f.category} placeholder={f.path.split(".")[0]} onChange={(e) => setF({ ...f, category: e.target.value })} />
            </Field>
          </div>
          <Field label="Value" htmlFor="t-val" hint='Text like 16px or 600ms, or JSON such as [0.22, 1, 0.36, 1]'>
            <Textarea id="t-val" rows={2} className="font-mono text-sm" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />
          </Field>
          <Field label="Description" htmlFor="t-desc">
            <Input id="t-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <Field label="Status" htmlFor="t-status">
            <StatusSelect label="Status" className="" value={f.status} onChange={(s) => setF({ ...f, status: s })} />
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.path || !f.value || save.isPending} onClick={() => save.mutate()}>
            {token ? "Save token" : "Create token"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TokenExport() {
  const ws = useWorkspace();
  const [fmt, setFmt] = React.useState<"css" | "dtcg" | "tailwind">("css");
  const [drafts, setDrafts] = React.useState(false);
  const q = useQuery({
    queryKey: ws.key("tokens-export", ws.brand.id, fmt, drafts),
    queryFn: async () => {
      const r = await ws.req<unknown>(`/v1/brands/${ws.brand.id}/design-tokens/export`, { params: { format: fmt, include_drafts: drafts || undefined } });
      return typeof r === "string" ? r : JSON.stringify(r, null, 2);
    },
  });
  const file = { css: `${ws.brand.slug}-tokens.css`, dtcg: `${ws.brand.slug}.tokens.json`, tailwind: `${ws.brand.slug}.tailwind.config.js` }[fmt];
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-4">
        <Segmented
          label="Export format"
          value={fmt}
          onChange={setFmt}
          options={[
            { value: "css", label: "CSS variables" },
            { value: "dtcg", label: "Design Tokens JSON" },
            { value: "tailwind", label: "Tailwind theme" },
          ]}
        />
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <Switch checked={drafts} onCheckedChange={setDrafts} aria-label="Include drafts" /> Include unapproved tokens
        </label>
      </div>
      <CodeBlock code={q.data ?? "…"} filename={file} label={drafts ? `${file} (includes drafts)` : `${file} (approved only)`} />
    </div>
  );
}

export function TokensSection({ domain, title = "Design tokens" }: { domain: "design_language" | "visual_identity"; title?: string }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const q = useDesignTokens();
  const [edit, setEdit] = React.useState<DesignToken | null>(null);
  const [open, setOpen] = React.useState(false);
  const canWrite = ws.can("knowledge.write");
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<DesignToken> }) => ws.req(`/v1/design-tokens/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ws.key("tokens") }),
  });
  const del = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/design-tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ws.key("tokens") }),
  });
  const tokens = (q.data?.items ?? []).filter((t) => t.domain_key === domain);
  const groups = new Map<string, DesignToken[]>();
  tokens.forEach((t) => groups.set(t.category, [...(groups.get(t.category) ?? []), t]));
  return (
    <>
      <Section
        title={title}
        description="Machine-readable values for spacing, radius, motion and more. Palette colors and type styles are exported as tokens automatically."
        actions={
          canWrite ? (
            <Button
              size="sm"
              onClick={() => {
                setEdit(null);
                setOpen(true);
              }}
            >
              <Plus /> Token
            </Button>
          ) : undefined
        }
      >
        {tokens.length ? (
          <Panel>
            <Table>
              <THead>
                <tr>
                  <th>Token</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th className="w-10" />
                  <th>Status</th>
                  <th className="w-0" />
                </tr>
              </THead>
              <TBody>
                {[...groups.entries()].map(([cat, ts]) => (
                  <React.Fragment key={cat}>
                    <tr>
                      <td colSpan={6} className="bg-surface-2 !py-1 text-sm text-muted">
                        {cat}
                      </td>
                    </tr>
                    {ts.map((t) => (
                      <tr key={t.id}>
                        <td className="font-mono text-[12px]">
                          {t.path}
                          {t.description ? <div className="font-sans text-sm text-muted">{t.description}</div> : null}
                        </td>
                        <td className="text-sm text-muted">{t.token_type}</td>
                        <td className="font-mono text-[12px]">{displayValue(t.value)}</td>
                        <td>
                          <TokenPreview t={t} />
                        </td>
                        <td>{canWrite ? <StatusSelect label={`Status of ${t.path}`} value={t.status} onChange={(s) => update.mutate({ id: t.id, body: { status: s as DesignToken["status"] } })} /> : <Status status={t.status} />}</td>
                        <td className="whitespace-nowrap">
                          {canWrite ? (
                            <>
                              <Button
                                size="icon-sm"
                                variant="ghost"
                                aria-label={`Edit ${t.path}`}
                                onClick={() => {
                                  setEdit(t);
                                  setOpen(true);
                                }}
                              >
                                <Pencil />
                              </Button>
                              <Button size="icon-sm" variant="ghost" aria-label={`Delete ${t.path}`} onClick={() => del.mutate(t.id)}>
                                <Trash2 />
                              </Button>
                            </>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </TBody>
            </Table>
          </Panel>
        ) : (
          <p className="text-base text-muted">No tokens in this domain yet.</p>
        )}
      </Section>
      <Section title="Developer and design-tool export" description="Generated from the approved palette, typography and tokens. Paste into a codebase, Figma Tokens or Style Dictionary.">
        <TokenExport />
      </Section>
      <TokenDialog token={edit} domain={domain} open={open} onOpenChange={setOpen} />
    </>
  );
}
