"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useTypography } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { TypeLevel, Typography } from "@/lib/types";
import { humanize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { EmptyState, LoadingBlock, Section } from "@/components/page";
import { Status } from "@/components/status";
import { useConfirm } from "@/components/confirm";
import { StatusSelect } from "./status-select";

const ROLES = ["display", "primary", "secondary", "body", "mono", "accent"] as const;

/** Load a Google-hosted family so the specimen shows the real face (other sources rely on local installation). */
function useGoogleFont(t: Typography) {
  React.useEffect(() => {
    if (t.source !== "google") return;
    const id = `gf-${t.family.replace(/\s+/g, "-")}`;
    if (document.getElementById(id)) return;
    const weights = (t.weights.length ? t.weights : [400]).slice().sort((a, b) => a - b).join(";");
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(t.family)}:wght@${weights}&display=swap`;
    document.head.appendChild(link);
  }, [t.family, t.source, t.weights]);
}

function Specimen({ t, onEdit, canWrite, onStatus, onDelete }: { t: Typography; onEdit: () => void; canWrite: boolean; onStatus: (s: string) => void; onDelete: () => void }) {
  useGoogleFont(t);
  const stack = `"${t.family}", ${t.fallback_stack}`;
  return (
    <article className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
        <h3 className="font-semibold">{t.name}</h3>
        <span className="text-sm text-muted">{humanize(t.role)}</span>
        {canWrite ? <StatusSelect label={`Status of ${t.name}`} value={t.status} onChange={onStatus} /> : <Status status={t.status} />}
        {canWrite ? (
          <span className="ml-auto flex gap-1">
            <Button size="icon-sm" variant="ghost" aria-label={`Edit ${t.name}`} onClick={onEdit}>
              <Pencil />
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label={`Delete ${t.name}`} onClick={onDelete}>
              <Trash2 />
            </Button>
          </span>
        ) : null}
      </header>
      <div className="grid gap-6 p-4 lg:grid-cols-[1fr_16rem]">
        <div className="min-w-0">
          <p className="truncate text-[56px] leading-none text-ink" style={{ fontFamily: stack, fontWeight: t.weights.at(-1) ?? 400 }}>
            {t.family}
          </p>
          <p className="mt-3 text-2xl text-ink-2" style={{ fontFamily: stack, fontWeight: t.weights[0] ?? 400 }}>
            Aa Bb Cc Dd Ee Ff Gg 0123456789 &amp;?!
          </p>
          {t.hierarchy.length ? (
            <div className="mt-6 grid gap-3">
              {t.hierarchy.map((l) => (
                <div key={l.level} className="grid grid-cols-[4.5rem_1fr] items-baseline gap-3">
                  <span className="text-xs text-muted">
                    {l.level}
                    <span className="block font-mono text-[10px]">
                      {l.size_px}/{Math.round(l.size_px * l.line_height)} · {l.weight}
                    </span>
                  </span>
                  <span
                    className="truncate text-ink"
                    style={{
                      fontFamily: stack,
                      fontSize: Math.min(l.size_px, 64),
                      lineHeight: l.line_height,
                      fontWeight: l.weight,
                      letterSpacing: l.letter_spacing_em ? `${l.letter_spacing_em}em` : undefined,
                      textTransform: (l.text_transform as React.CSSProperties["textTransform"]) ?? undefined,
                    }}
                  >
                    {l.usage || "The quick brown fox jumps over the lazy dog"}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <dl className="grid content-start gap-2 text-sm">
          <div>
            <dt className="text-muted">Weights</dt>
            <dd>{t.weights.join(", ") || "—"}{t.supports_italic ? " + italic" : ""}</dd>
          </div>
          <div>
            <dt className="text-muted">Fallback stack</dt>
            <dd className="font-mono text-[11px]">{t.fallback_stack}</dd>
          </div>
          <div>
            <dt className="text-muted">Source and license</dt>
            <dd>
              {t.source ? humanize(t.source) : "—"}
              {t.license ? ` · ${t.license}` : ""}
            </dd>
          </div>
          {t.usage ? (
            <div>
              <dt className="text-muted">Usage</dt>
              <dd>{t.usage}</dd>
            </div>
          ) : null}
          {t.source !== "google" ? <dd className="text-xs text-muted">Shown with the fallback stack if the face is not installed on this device.</dd> : null}
        </dl>
      </div>
    </article>
  );
}

function TypographyDialog({ t, open, onOpenChange }: { t: Typography | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const blank = { name: "", role: "body", family: "", fallback_stack: "system-ui, sans-serif", source: "google", source_url: "", license: "", weights: "400, 700", supports_italic: false, usage: "", hierarchy: [] as TypeLevel[] };
  const [f, setF] = useResetState([open, t?.id], () =>
    t
      ? { name: t.name, role: t.role, family: t.family, fallback_stack: t.fallback_stack, source: t.source ?? "", source_url: t.source_url ?? "", license: t.license ?? "", weights: t.weights.join(", "), supports_italic: t.supports_italic, usage: t.usage ?? "", hierarchy: t.hierarchy }
      : blank,
  );
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...f,
        weights: f.weights.split(",").map((w) => parseInt(w.trim(), 10)).filter((n) => !isNaN(n)),
        source: f.source || null,
        source_url: f.source_url || null,
        license: f.license || null,
        usage: f.usage || null,
        hierarchy: f.hierarchy.filter((l) => l.level),
      };
      return t ? ws.req(`/v1/typography/${t.id}`, { method: "PATCH", body }) : ws.req(`/v1/brands/${ws.brand.id}/typography`, { method: "POST", body: { ...body, status: "draft" } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("typography") });
      qc.invalidateQueries({ queryKey: ws.key("domain") });
      toast.success(t ? "Typography updated" : "Typography created as draft");
      onOpenChange(false);
    },
    onError: () => {},
  });
  const setLevel = (i: number, k: keyof TypeLevel, v: string) =>
    setF((s) => ({ ...s, hierarchy: s.hierarchy.map((l, j) => (j === i ? { ...l, [k]: ["level", "usage", "text_transform"].includes(k) ? v : parseFloat(v) || 0 } : l)) }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader title={t ? `Edit ${t.name}` : "New typography system"} />
        <DialogBody className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name" htmlFor="ty-name">
              <Input id="ty-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </Field>
            <Field label="Role" htmlFor="ty-role">
              <NativeSelect id="ty-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {humanize(r)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Family" htmlFor="ty-fam">
              <Input id="ty-fam" value={f.family} onChange={(e) => setF({ ...f, family: e.target.value })} />
            </Field>
            <Field label="Fallback stack" htmlFor="ty-fb" className="sm:col-span-2">
              <Input id="ty-fb" className="font-mono text-sm" value={f.fallback_stack} onChange={(e) => setF({ ...f, fallback_stack: e.target.value })} />
            </Field>
            <Field label="Weights" htmlFor="ty-w" hint="Comma separated">
              <Input id="ty-w" value={f.weights} onChange={(e) => setF({ ...f, weights: e.target.value })} />
            </Field>
            <Field label="Source" htmlFor="ty-src">
              <NativeSelect id="ty-src" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
                {["google", "adobe", "foundry", "custom", "system"].map((s) => (
                  <option key={s} value={s}>
                    {humanize(s)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="License" htmlFor="ty-lic">
              <Input id="ty-lic" value={f.license} onChange={(e) => setF({ ...f, license: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 self-end pb-1.5 text-base">
              <Switch checked={f.supports_italic} onCheckedChange={(v) => setF({ ...f, supports_italic: v })} /> Italic available
            </label>
          </div>
          <div className="grid gap-2">
            <Label>Hierarchy</Label>
            {f.hierarchy.map((l, i) => (
              <div key={i} className="grid grid-cols-[5rem_5rem_5rem_5rem_1fr_auto] gap-1.5">
                <Input aria-label="Level" placeholder="h1" value={l.level} onChange={(e) => setLevel(i, "level", e.target.value)} />
                <Input aria-label="Size (px)" type="number" placeholder="px" value={l.size_px} onChange={(e) => setLevel(i, "size_px", e.target.value)} />
                <Input aria-label="Line height" type="number" step="0.05" placeholder="1.2" value={l.line_height} onChange={(e) => setLevel(i, "line_height", e.target.value)} />
                <Input aria-label="Weight" type="number" step="100" placeholder="400" value={l.weight} onChange={(e) => setLevel(i, "weight", e.target.value)} />
                <Input aria-label="Usage" placeholder="Where it is used" value={l.usage ?? ""} onChange={(e) => setLevel(i, "usage", e.target.value)} />
                <Button size="icon" variant="ghost" aria-label="Remove level" onClick={() => setF((s) => ({ ...s, hierarchy: s.hierarchy.filter((_, j) => j !== i) }))}>
                  <X />
                </Button>
              </div>
            ))}
            <Button size="sm" variant="ghost" className="justify-self-start" onClick={() => setF((s) => ({ ...s, hierarchy: [...s.hierarchy, { level: "", size_px: 16, line_height: 1.5, weight: 400 }] }))}>
              <Plus /> Add level
            </Button>
          </div>
          <Field label="Usage notes" htmlFor="ty-use">
            <Textarea id="ty-use" rows={2} value={f.usage} onChange={(e) => setF({ ...f, usage: e.target.value })} />
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name || !f.family || save.isPending} onClick={() => save.mutate()}>
            Save typography
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TypographySection() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = useTypography();
  const canWrite = ws.can("knowledge.write");
  const [dlg, setDlg] = React.useState<{ t: Typography | null } | null>(null);
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Typography> }) => ws.req(`/v1/typography/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ws.key("typography") }),
  });
  const del = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/typography/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ws.key("typography") }),
  });
  return (
    <Section
      title="Typography"
      description="Families, weights and the typographic hierarchy, rendered as specimens."
      actions={
        canWrite ? (
          <Button size="sm" onClick={() => setDlg({ t: null })}>
            <Plus /> Typeface
          </Button>
        ) : undefined
      }
    >
      {!q.data ? (
        <LoadingBlock rows={3} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No typography defined yet" />
      ) : (
        <div className="grid gap-4">
          {q.data.items.map((t) => (
            <Specimen
              key={t.id}
              t={t}
              canWrite={canWrite}
              onEdit={() => setDlg({ t })}
              onStatus={(s) => patch.mutate({ id: t.id, body: { status: s as Typography["status"] } })}
              onDelete={async () => {
                if (await confirm({ title: `Delete ${t.name}?`, confirmLabel: "Delete typeface", destructive: true })) del.mutate(t.id);
              }}
            />
          ))}
        </div>
      )}
      <TypographyDialog t={dlg?.t ?? null} open={!!dlg} onOpenChange={(o) => !o && setDlg(null)} />
    </Section>
  );
}
