"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { usePalettes } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { ColorToken, ContrastPair, Palette } from "@/lib/types";
import { cn, humanize, onColor } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { EmptyState, LoadingBlock, MetaList, Section } from "@/components/page";
import { CopyValue } from "@/components/code-block";
import { Status } from "@/components/status";
import { useConfirm } from "@/components/confirm";
import { StatusSelect } from "./status-select";
import { sortPalettes } from "@/components/dna-strip";

const ROLES = ["primary", "secondary", "accent", "neutral", "semantic", "extended"] as const;

function Swatch({ c, onOpen }: { c: ColorToken; onOpen: () => void }) {
  const ink = onColor(c.hex);
  return (
    <button onClick={onOpen} className="group flex w-36 shrink-0 flex-col overflow-hidden rounded-md border border-line bg-surface text-left focus-visible:outline-2 focus-visible:outline-ring">
      <span className="flex h-24 items-end p-2 text-sm font-medium" style={{ background: c.hex, color: ink }}>
        {c.name}
      </span>
      <span className="grid gap-0.5 px-2 py-1.5">
        <span className="font-mono text-[12px] uppercase text-ink">{c.hex}</span>
        <span className="truncate font-mono text-[11px] text-muted">{c.oklch.css}</span>
        {c.usage ? <span className="line-clamp-2 text-xs text-muted">{c.usage}</span> : null}
      </span>
    </button>
  );
}

function ColorDialog({ palette, color, open, onOpenChange }: { palette: Palette | null; color: ColorToken | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open, color?.id], () =>
      color
        ? {
            name: color.name,
            hex: color.hex,
            token_key: color.token_key,
            pantone: color.pantone ?? "",
            semantic_role: color.semantic_role ?? "",
            usage: color.usage ?? "",
            cmyk: color.cmyk_is_manual ? [color.cmyk.c, color.cmyk.m, color.cmyk.y, color.cmyk.k].join(", ") : "",
          }
        : { name: "", hex: "#", token_key: "", pantone: "", semantic_role: "", usage: "", cmyk: "" },
  );
  const validHex = /^#?[0-9a-fA-F]{6}$/.test(f.hex.trim());
  const conv = useQuery({
    queryKey: ws.key("convert", f.hex),
    queryFn: () => ws.req<ColorToken & { contrast: unknown[] }>("/v1/colors/convert", { params: { hex: f.hex.trim(), against: ["#ffffff", "#000000"] } }),
    enabled: open && validHex,
  });
  const save = useMutation({
    mutationFn: () => {
      const cm = f.cmyk.split(",").map((x) => parseFloat(x.trim()));
      const body = {
        name: f.name,
        hex: f.hex.trim(),
        token_key: f.token_key || undefined,
        pantone: f.pantone || null,
        semantic_role: f.semantic_role || null,
        usage: f.usage || null,
        cmyk: cm.length === 4 && cm.every((n) => !isNaN(n)) ? { c: cm[0], m: cm[1], y: cm[2], k: cm[3] } : undefined,
      };
      return color ? ws.req(`/v1/colors/${color.id}`, { method: "PATCH", body }) : ws.req(`/v1/palettes/${palette!.id}/colors`, { method: "POST", body: { ...body, sort_order: palette!.colors.length } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("palettes") });
      qc.invalidateQueries({ queryKey: ws.key("domain") });
      toast.success(color ? "Color updated" : "Color added");
      onOpenChange(false);
    },
    onError: () => {},
  });
  const c = conv.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader title={color ? `Edit ${color.name}` : `Add a color to ${palette?.name ?? ""}`} description="RGB, HSL and OKLCH are computed from the HEX value. CMYK is an approximation unless you enter the printer's values." />
        <DialogBody className="grid gap-4 sm:grid-cols-[1fr_12rem]">
          <div className="grid content-start gap-3">
            <Field label="Name" htmlFor="c-name">
              <Input id="c-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </Field>
            <Field label="HEX" htmlFor="c-hex">
              <div className="flex gap-2">
                <input type="color" aria-label="Pick color" className="h-8 w-10 cursor-pointer rounded border border-line-strong bg-surface" value={validHex ? (f.hex.startsWith("#") ? f.hex : "#" + f.hex) : "#000000"} onChange={(e) => setF({ ...f, hex: e.target.value })} />
                <Input id="c-hex" className="font-mono" value={f.hex} onChange={(e) => setF({ ...f, hex: e.target.value })} aria-invalid={!validHex && f.hex.length > 1} />
              </div>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Token key" htmlFor="c-key" hint="Default: color.<role>.<name>">
                <Input id="c-key" className="font-mono text-sm" value={f.token_key} onChange={(e) => setF({ ...f, token_key: e.target.value })} />
              </Field>
              <Field label="Pantone" htmlFor="c-pan">
                <Input id="c-pan" value={f.pantone} onChange={(e) => setF({ ...f, pantone: e.target.value })} />
              </Field>
              <Field label="Semantic role" htmlFor="c-sem" hint="e.g. success, link, surface">
                <Input id="c-sem" value={f.semantic_role} onChange={(e) => setF({ ...f, semantic_role: e.target.value })} />
              </Field>
              <Field label="Print CMYK" htmlFor="c-cmyk" hint="c, m, y, k (0–100). Empty = approximate.">
                <Input id="c-cmyk" value={f.cmyk} onChange={(e) => setF({ ...f, cmyk: e.target.value })} />
              </Field>
            </div>
            <Field label="Usage" htmlFor="c-use">
              <Textarea id="c-use" rows={2} value={f.usage} onChange={(e) => setF({ ...f, usage: e.target.value })} />
            </Field>
            {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
          </div>
          <div className="grid content-start gap-2">
            <div className="h-28 rounded-md border border-line" style={{ background: validHex ? (f.hex.startsWith("#") ? f.hex : "#" + f.hex) : "transparent" }} />
            {c ? (
              <dl className="grid gap-1 font-mono text-[11px] text-ink-2">
                <dt className="text-muted">RGB</dt>
                <dd>{c.rgb.css}</dd>
                <dt className="text-muted">HSL</dt>
                <dd>{c.hsl.css}</dd>
                <dt className="text-muted">OKLCH</dt>
                <dd>{c.oklch.css}</dd>
                <dt className="text-muted">CMYK ≈</dt>
                <dd>
                  {c.cmyk.c} {c.cmyk.m} {c.cmyk.y} {c.cmyk.k}
                </dd>
              </dl>
            ) : null}
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name || !validHex || save.isPending} onClick={() => save.mutate()}>
            {color ? "Save color" : "Add color"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ColorDetail({ color, onClose, onEdit, onDelete, canWrite }: { color: ColorToken | null; onClose: () => void; onEdit: () => void; onDelete: () => void; canWrite: boolean }) {
  return (
    <Dialog open={!!color} onOpenChange={(o) => !o && onClose()}>
      {color ? (
        <DialogContent size="sm">
          <div className="flex h-32 items-end p-4 text-lg font-semibold" style={{ background: color.hex, color: onColor(color.hex) }}>
            {color.name}
          </div>
          <DialogHeader title={color.name} description={color.usage ?? undefined} className="sr-only" />
          <DialogBody>
            <MetaList
              items={[
                ["HEX", <CopyValue key="h" value={color.hex.toUpperCase()} />],
                ["RGB", <CopyValue key="r" value={color.rgb.css ?? `${color.rgb.r} ${color.rgb.g} ${color.rgb.b}`} />],
                ["HSL", <CopyValue key="s" value={color.hsl.css ?? ""} />],
                ["OKLCH", <CopyValue key="o" value={color.oklch.css} />],
                ["CMYK", <span key="c">{`${color.cmyk.c} / ${color.cmyk.m} / ${color.cmyk.y} / ${color.cmyk.k}`}<span className="text-muted">{color.cmyk.approximate ? " (approximate)" : " (from printer)"}</span></span>],
                ["Pantone", color.pantone],
                ["Token", <CopyValue key="t" value={color.token_key} />],
                ["CSS variable", <CopyValue key="v" value={`var(--${color.token_key.replace(/\./g, "-")})`} />],
                ["Semantic role", color.semantic_role],
                ["Usage", color.usage],
              ]}
            />
          </DialogBody>
          {canWrite ? (
            <DialogFooter>
              <Button variant="ghost" onClick={onDelete}>
                <Trash2 /> Delete
              </Button>
              <Button onClick={onEdit}>
                <Pencil /> Edit
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function PaletteDialog({ palette, open, onOpenChange }: { palette: Palette | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open, palette?.id], () =>
    palette ? { name: palette.name, role: palette.role, description: palette.description ?? "" } : { name: "", role: "primary", description: "" },
  );
  const save = useMutation({
    mutationFn: () =>
      palette
        ? ws.req(`/v1/palettes/${palette.id}`, { method: "PATCH", body: { ...f, description: f.description || null } })
        : ws.req(`/v1/brands/${ws.brand.id}/palettes`, { method: "POST", body: { ...f, description: f.description || null, status: "draft" } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("palettes") });
      toast.success(palette ? "Palette updated" : "Palette created as draft");
      onOpenChange(false);
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader title={palette ? "Edit palette" : "New palette"} />
        <DialogBody className="grid gap-3">
          <Field label="Name" htmlFor="pl-name">
            <Input id="pl-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Role" htmlFor="pl-role">
            <NativeSelect id="pl-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Description" htmlFor="pl-desc">
            <Textarea id="pl-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name || save.isPending} onClick={() => save.mutate()}>
            Save palette
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ContrastMatrix({ pairs, colors }: { pairs: ContrastPair[]; colors: ColorToken[] }) {
  const look = new Map<string, ContrastPair>();
  pairs.forEach((p) => {
    look.set(`${p.a_hex}|${p.b_hex}`, p);
    look.set(`${p.b_hex}|${p.a_hex}`, p);
  });
  const cs = colors.slice(0, 12);
  if (cs.length < 2) return <p className="text-muted">Add at least two colors to check contrast.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5 text-xs">
        <caption className="sr-only">WCAG contrast ratio of every color pair</caption>
        <thead>
          <tr>
            <th />
            {cs.map((c) => (
              <th key={c.id} scope="col" className="w-16 px-1 pb-1 text-left font-normal text-muted">
                <span className="mb-1 block h-2 rounded-sm border border-line" style={{ background: c.hex }} />
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cs.map((row) => (
            <tr key={row.id}>
              <th scope="row" className="pr-2 text-left font-normal text-muted">
                {row.name}
              </th>
              {cs.map((col) => {
                if (row.id === col.id) return <td key={col.id} className="bg-sunken" />;
                const p = look.get(`${row.hex}|${col.hex}`);
                const ratio = p?.ratio;
                const level = !p ? "" : p.AAA_normal ? "AAA" : p.AA_normal ? "AA" : p.AA_large ? "AA large" : "Fails";
                return (
                  <td
                    key={col.id}
                    className="h-10 rounded-sm px-1 text-center align-middle"
                    style={{ background: col.hex, color: row.hex }}
                    title={`${row.name} on ${col.name}: ${ratio ?? "?"}:1 — ${level}`}
                  >
                    <span className="font-semibold">{ratio ? ratio.toFixed(1) : "—"}</span>
                    <span className={cn("block text-[9px]", level === "Fails" && "line-through")}>{level}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-sm text-muted">Each cell shows the row color as text on the column color. AA needs 4.5:1 for body text, 3:1 for large text.</p>
    </div>
  );
}

export function PalettesSection() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const q = usePalettes();
  const canWrite = ws.can("knowledge.write");
  const [colorDlg, setColorDlg] = React.useState<{ palette: Palette | null; color: ColorToken | null } | null>(null);
  const [detail, setDetail] = React.useState<ColorToken | null>(null);
  const [palDlg, setPalDlg] = React.useState<{ palette: Palette | null } | null>(null);
  const invalidate = () => qc.invalidateQueries({ queryKey: ws.key("palettes") });
  const patchPalette = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Palette> }) => ws.req(`/v1/palettes/${id}`, { method: "PATCH", body }),
    onSuccess: invalidate,
  });
  const delPalette = useMutation({ mutationFn: (id: string) => ws.req(`/v1/palettes/${id}`, { method: "DELETE" }), onSuccess: invalidate });
  const delColor = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/colors/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      setDetail(null);
    },
  });
  if (!q.data) return <LoadingBlock rows={3} />;
  const all = sortPalettes(q.data.items).flatMap((p) => p.colors);
  return (
    <>
      <Section
        title="Color"
        description="Approved palettes are what context packages, token exports and MCP clients receive."
        actions={
          canWrite ? (
            <Button size="sm" onClick={() => setPalDlg({ palette: null })}>
              <Plus /> Palette
            </Button>
          ) : undefined
        }
      >
        {q.data.items.length === 0 ? (
          <EmptyState title="No palettes yet">Start with the primary palette; accents and semantic colors can follow.</EmptyState>
        ) : (
          <div className="grid gap-8">
            {sortPalettes(q.data.items).map((p) => (
              <div key={p.id}>
                <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <h3 className="text-md font-semibold">{p.name}</h3>
                  <span className="text-sm text-muted">{humanize(p.role)}</span>
                  {canWrite ? (
                    <StatusSelect label={`Status of ${p.name}`} value={p.status} onChange={(s) => patchPalette.mutate({ id: p.id, body: { status: s as Palette["status"] } })} />
                  ) : (
                    <Status status={p.status} />
                  )}
                  {canWrite ? (
                    <span className="ml-auto flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setColorDlg({ palette: p, color: null })}>
                        <Plus /> Color
                      </Button>
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setPalDlg({ palette: p })}>
                        <Pencil />
                      </Button>
                      {p.status !== "approved" ? (
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Delete ${p.name}`}
                          onClick={async () => {
                            if (await confirm({ title: `Delete ${p.name}?`, description: "The palette and its colors are removed.", confirmLabel: "Delete palette", destructive: true })) delPalette.mutate(p.id);
                          }}
                        >
                          <Trash2 />
                        </Button>
                      ) : null}
                    </span>
                  ) : null}
                </div>
                {p.description ? <p className="mb-2 text-base text-ink-2">{p.description}</p> : null}
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {p.colors.map((c) => (
                    <Swatch key={c.id} c={c} onOpen={() => setDetail(c)} />
                  ))}
                  {p.colors.length === 0 ? <p className="text-sm text-muted">No colors in this palette yet.</p> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
      {all.length > 1 ? (
        <Section title="Accessibility and contrast" description="WCAG 2.2 contrast between every pair of brand colors.">
          <ContrastMatrix pairs={q.data.accessibility} colors={all} />
        </Section>
      ) : null}
      <ColorDialog palette={colorDlg?.palette ?? null} color={colorDlg?.color ?? null} open={!!colorDlg} onOpenChange={(o) => !o && setColorDlg(null)} />
      <PaletteDialog palette={palDlg?.palette ?? null} open={!!palDlg} onOpenChange={(o) => !o && setPalDlg(null)} />
      <ColorDetail
        color={detail}
        canWrite={canWrite}
        onClose={() => setDetail(null)}
        onEdit={() => {
          const pal = q.data!.items.find((p) => p.id === detail?.palette_id) ?? null;
          setColorDlg({ palette: pal, color: detail });
          setDetail(null);
        }}
        onDelete={async () => {
          if (detail && (await confirm({ title: `Delete ${detail.name}?`, confirmLabel: "Delete color", destructive: true }))) delColor.mutate(detail.id);
        }}
      />
    </>
  );
}
