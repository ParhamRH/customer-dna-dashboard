"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileArchive, PackagePlus, ShieldCheck, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { request, upload, errorMessage } from "@/lib/api";
import type { Brand, Collection, ExportJob, ImportJob, Project, Registry } from "@/lib/types";
import { cn, formatBytes, formatDateTime, formatNumber, humanize, relativeTime } from "@/lib/utils";
import { PROJECT_TYPE_LABELS } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/tabs";
import { TBody, THead, Table } from "@/components/ui/misc";
import { EmptyState, ErrorState, LoadingBlock, MetaList, Panel } from "@/components/page";
import { Status, Tag } from "@/components/status";
import { CopyValue } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

function useBrands(org: string) {
  return useQuery({ queryKey: ["ws", org, "brands"], queryFn: () => request<{ items: Brand[] }>("/v1/brands", { org }) });
}

export async function openSignedDownload(path: string, org: string) {
  const d = await request<{ url: string }>(path, { org });
  const a = document.createElement("a");
  a.href = d.url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* ------------------------------------------------------------------------------------------- */
export function ExportsPanel({ org, canCreate = true, canDownload = true }: { org: string; canCreate?: boolean; canDownload?: boolean }) {
  const key = ["ws", org, "exports"];
  const q = useQuery({
    queryKey: key,
    queryFn: () => request<{ items: ExportJob[] }>("/v1/exports", { org }),
    refetchInterval: (query) =>
      query.state.data?.items.some((e) => e.status === "queued" || e.status === "running") ? 2000 : false,
  });
  const [open, setOpen] = React.useState(false);
  const [detail, setDetail] = React.useState<ExportJob | null>(null);

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      {canCreate ? (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setOpen(true)}>
            <PackagePlus /> New export
          </Button>
        </div>
      ) : null}
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {!q.data ? (
        <LoadingBlock rows={3} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No exports yet" icon={<FileArchive />}>
          A full export packages this customer&apos;s complete library — knowledge, assets, relationships and a checksummed manifest — as
          one ZIP that never contains another customer&apos;s data.
        </EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Requested</th>
                <th>Mode</th>
                <th>Brands</th>
                <th>Domains</th>
                <th className="text-right">Files</th>
                <th className="text-right">Size</th>
                <th>Status</th>
                <th className="w-0">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((e) => {
                const sel = (e.options?.selection ?? {}) as { domains?: string[] };
                return (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap">
                      <button className="text-left hover:underline" onClick={() => setDetail(e)}>
                        {formatDateTime(e.created_at)}
                      </button>
                    </td>
                    <td>{e.mode === "full" ? "Complete library" : "Selective"}</td>
                    <td className="text-sm">{e.brand_names.join(", ") || "—"}</td>
                    <td className="text-sm text-muted">{e.mode === "full" ? "All" : (sel.domains ?? []).map(humanize).join(", ") || "Selection"}</td>
                    <td className="tabular text-right">{formatNumber(e.file_count)}</td>
                    <td className="tabular text-right">{formatBytes(e.size_bytes)}</td>
                    <td>
                      <Status status={e.status} />
                      {e.status === "completed" && e.expires_at ? (
                        <div className="text-xs text-muted">expires {relativeTime(e.expires_at).replace(" ago", "")}</div>
                      ) : null}
                    </td>
                    <td>
                      {e.download_available && canDownload ? (
                        <Button
                          size="sm"
                          onClick={() => openSignedDownload(`/v1/exports/${e.id}/download`, org).catch((err) => toast.error(errorMessage(err)))}
                        >
                          <Download /> Download
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
      <NewExportDialog org={org} open={open} onOpenChange={setOpen} />
      <ExportDetail exp={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

function ExportDetail({ exp, onClose }: { exp: ExportJob | null; onClose: () => void }) {
  const m = (exp?.manifest ?? {}) as Record<string, unknown>;
  return (
    <Dialog open={!!exp} onOpenChange={(o) => !o && onClose()}>
      {exp ? (
        <DialogContent size="md">
          <DialogHeader title="Export manifest" description="Recorded when the archive was built. The ZIP's manifest.json lists a SHA-256 for every file." />
          <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
            <MetaList
              items={[
                ["Export ID", <CopyValue key="id" value={exp.id} />],
                ["Mode", exp.mode === "full" ? "Complete library" : "Selective"],
                ["Status", <Status key="s" status={exp.status} />],
                ["Brands", exp.brand_names.join(", ")],
                ["Files", formatNumber(exp.file_count)],
                ["Size", formatBytes(exp.size_bytes)],
                ["Archive SHA-256", exp.archive_checksum ? <CopyValue key="c" value={exp.archive_checksum} display={exp.archive_checksum.slice(0, 24) + "…"} /> : null],
                ["Schema version", m.schema_version as string],
                ["Asset count", m.asset_count as number],
                ["Included domains", Array.isArray(m.included_domains) ? (m.included_domains as string[]).map(humanize).join(", ") : null],
                [
                  "Tenant purity check",
                  m.tenant_purity_check ? (
                    <span key="t" className="inline-flex items-center gap-1.5 text-accent">
                      <ShieldCheck className="size-4" /> {(m.tenant_purity_check as { passed?: boolean }).passed ? "Passed — no other customer's identifiers" : "Failed"}
                    </span>
                  ) : null,
                ],
                ["Completed", formatDateTime(exp.completed_at)],
                ["Expires", formatDateTime(exp.expires_at)],
                ["Error", exp.error],
              ]}
            />
            {Array.isArray(m.embeddings) && (m.embeddings as unknown[]).length ? (
              <p className="text-sm text-muted">
                Embeddings are included with their model and dimensions. They are only reused on import when the target installation runs the
                same model; otherwise they are regenerated.
              </p>
            ) : null}
          </DialogBody>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

export function NewExportDialog({ org, open, onOpenChange }: { org: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const brands = useBrands(org);
  const registry = useQuery({ queryKey: ["ws", org, "registry"], queryFn: () => request<Registry>("/v1/knowledge/registry", { org }), enabled: open });
  const [mode, setMode] = React.useState<"full" | "selective">("full");
  const [brandIds, setBrandIds] = React.useState<string[]>([]);
  const [brandId, setBrandId] = React.useState("");
  const [domains, setDomains] = React.useState<string[]>([]);
  const [collections, setCollections] = React.useState<string[]>([]);
  const [projectId, setProjectId] = React.useState("");
  const [opts, setOpts] = React.useState({ include_originals: true, include_derivatives: true, include_ai_knowledge: true, include_embeddings: false, include_pending: true });
  const sel = brandId || brands.data?.items[0]?.id || "";
  const colls = useQuery({
    queryKey: ["ws", org, "collections", sel],
    queryFn: () => request<{ items: Collection[] }>(`/v1/brands/${sel}/collections`, { org }),
    enabled: open && mode === "selective" && !!sel,
  });
  const projects = useQuery({
    queryKey: ["ws", org, "projects", sel],
    queryFn: () => request<{ items: Project[] }>(`/v1/brands/${sel}/projects`, { org }),
    enabled: open && mode === "selective" && !!sel,
  });
  const create = useMutation({
    mutationFn: () =>
      request<ExportJob>("/v1/exports", {
        method: "POST",
        org,
        body:
          mode === "full"
            ? { mode, brand_ids: brandIds, ...opts }
            : {
                mode,
                selection: { brand_id: sel, domains, collection_ids: collections, project_id: projectId || null },
                ...opts,
              },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ws", org, "exports"] });
      qc.invalidateQueries({ queryKey: ["admin"] });
      toast.success("Export started. It appears in the list when the archive is ready.");
      onOpenChange(false);
    },
    onError: () => {},
  });
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const domainList = registry.data?.domains.filter((d) => !["creative_assets", "ai_knowledge"].includes(d.key)) ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader title="New export" description="Exports only this customer's data. The archive is built in the background." />
        <DialogBody className="grid gap-5">
          <Segmented
            label="Export mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "full", label: "Complete library" },
              { value: "selective", label: "Selective creative context" },
            ]}
          />
          {mode === "full" ? (
            <div className="grid gap-2">
              <Label>Brands</Label>
              <p className="-mt-1 text-sm text-muted">Leave all unchecked to export every brand of the customer.</p>
              {brands.data?.items.map((b) => (
                <label key={b.id} className="flex items-center gap-2 text-base">
                  <Checkbox checked={brandIds.includes(b.id)} onCheckedChange={() => toggle(brandIds, setBrandIds, b.id)} /> {b.name}
                </label>
              ))}
            </div>
          ) : (
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
              <Field label="Brand" htmlFor="ex-brand">
                <NativeSelect id="ex-brand" value={sel} onChange={(e) => setBrandId(e.target.value)}>
                  {brands.data?.items.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <div className="grid gap-2">
                <Label>Knowledge domains</Label>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {domainList.map((d) => (
                    <label key={d.key} className="flex items-center gap-2 text-base">
                      <Checkbox checked={domains.includes(d.key)} onCheckedChange={() => toggle(domains, setDomains, d.key)} /> {d.name}
                    </label>
                  ))}
                </div>
              </div>
              {colls.data?.items.length ? (
                <div className="grid gap-2">
                  <Label>Collections (their assets are included)</Label>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {colls.data.items.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-base">
                        <Checkbox checked={collections.includes(c.id)} onCheckedChange={() => toggle(collections, setCollections, c.id)} /> {c.name}
                        <span className="text-sm text-muted">{c.asset_count}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
              <Field label="Project" htmlFor="ex-proj" hint="Adds the project and the assets it uses.">
                <NativeSelect id="ex-proj" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">No project</option>
                  {projects.data?.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({PROJECT_TYPE_LABELS[p.project_type] ?? p.project_type})
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            </div>
          )}
          <div className="grid gap-2 border-t border-line pt-4">
            <Label>Contents</Label>
            {(
              [
                ["include_originals", "Original files", "Untouched originals, verified by checksum"],
                ["include_derivatives", "Previews and derived media", "Thumbnails, keyframes, page renders"],
                ["include_ai_knowledge", "AI analysis records", "Kept separate from approved knowledge"],
                ["include_pending", "Drafts and pending items", "Otherwise only approved knowledge is exported"],
                ["include_embeddings", "Vector embeddings", "Recorded with model and dimensions; re-generated on import if models differ"],
              ] as const
            ).map(([k, label, hint]) => (
              <label key={k} className="flex items-start gap-2 text-base">
                <Checkbox className="mt-0.5" checked={opts[k]} onCheckedChange={(v) => setOpts((s) => ({ ...s, [k]: !!v }))} />
                <span>
                  {label}
                  <span className="block text-sm text-muted">{hint}</span>
                </span>
              </label>
            ))}
          </div>
          {create.error ? <p className="text-sm text-danger">{errorMessage(create.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={create.isPending || (mode === "selective" && !sel)} onClick={() => create.mutate()}>
            {create.isPending ? "Starting…" : "Start export"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------------------------------- */
type Preview = {
  source?: Record<string, unknown> & { note?: string };
  checksums_verified?: number;
  errors?: string[];
  warnings?: string[];
  brands?: { source_id: string; name: string; slug: string; conflict_brand_id: string | null }[];
  duplicates?: { assets: number; items: { title: string }[] };
  counts?: Record<string, number>;
  embeddings?: { included: boolean; compatible: boolean; current_text_model: { model: string; dimensions: number } };
};

export function ImportsPanel({ org }: { org: string }) {
  const qc = useQueryClient();
  const key = ["ws", org, "imports"];
  const q = useQuery({
    queryKey: key,
    queryFn: () => request<{ items: ImportJob[] }>("/v1/imports", { org }),
    refetchInterval: (query) => (query.state.data?.items.some((i) => ["uploaded", "validating", "committing"].includes(i.status)) ? 2000 : false),
  });
  const [progress, setProgress] = React.useState<number | null>(null);
  const [active, setActive] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function onFile(f: File | undefined) {
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    setProgress(0);
    try {
      const ij = await upload<ImportJob>("/v1/imports", form, { org, onProgress: setProgress });
      setActive(ij.id);
      qc.invalidateQueries({ queryKey: key });
      toast.success("Archive uploaded. Validating checksums and schema…");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setProgress(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const current = q.data?.items.find((i) => i.id === active) ?? null;

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-base text-muted">
          Import a library exported from this or another compatible installation. Nothing is written until you review the preview and commit;
          the commit runs in a single transaction and rolls back completely on any error.
        </p>
        <div>
          <input ref={fileRef} type="file" accept=".zip,application/zip" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
          <Button onClick={() => fileRef.current?.click()} disabled={progress !== null}>
            <Upload /> {progress !== null ? `Uploading ${Math.round(progress * 100)}%` : "Upload export archive"}
          </Button>
        </div>
      </div>
      {q.data?.items.length ? (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Uploaded</th>
                <th>Archive</th>
                <th>Status</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((i) => (
                <tr key={i.id} className={cn(i.id === active && "bg-surface-2")}>
                  <td className="whitespace-nowrap">{formatDateTime(i.created_at)}</td>
                  <td className="text-sm">{String(i.options?.filename ?? "archive.zip")}</td>
                  <td>
                    <Status status={i.status} />
                  </td>
                  <td>
                    <Button size="sm" variant="ghost" onClick={() => setActive(i.id)}>
                      Review
                    </Button>
                  </td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      ) : null}
      {current ? <ImportReview org={org} ij={current} onDone={() => setActive(null)} /> : null}
    </div>
  );
}

function ImportReview({ org, ij, onDone }: { org: string; ij: ImportJob; onDone: () => void }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const brands = useBrands(org);
  const p = ij.preview as Preview;
  const [mapping, setMapping] = React.useState<Record<string, string>>({});
  const [opts, setOpts] = React.useState({ skip_duplicate_assets: true, import_ai_knowledge: true, preserve_approvals: true, regenerate_embeddings: true });
  const commit = useMutation({
    mutationFn: () => request(`/v1/imports/${ij.id}/commit`, { method: "POST", org, body: { brand_mapping: mapping, ...opts } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ws", org] });
      toast.success("Import committing in the background");
    },
  });
  const discard = useMutation({
    mutationFn: () => request(`/v1/imports/${ij.id}`, { method: "DELETE", org }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ws", org, "imports"] });
      onDone();
    },
  });
  const report = ij.report as { errors?: string[]; warnings?: string[]; created?: Record<string, number>; skipped?: Record<string, number> };

  return (
    <Panel className="grid gap-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">Import preview</h3>
        <Status status={ij.status} />
      </div>
      {["uploaded", "validating"].includes(ij.status) ? <LoadingBlock rows={2} /> : null}
      {p?.errors?.length ? (
        <div className="rounded-md border border-danger/30 bg-danger-soft p-3 text-base">
          <p className="font-medium text-danger">This archive cannot be imported</p>
          <ul className="mt-1 list-disc pl-5 text-ink-2">
            {p.errors.slice(0, 10).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {p?.source ? (
        <MetaList
          items={[
            ["Source customer", String(p.source.customer_slug ?? p.source.customer_id ?? "—")],
            ["Exported", formatDateTime(p.source.export_date as string)],
            ["Mode", String(p.source.export_mode ?? "—")],
            ["Schema", String(p.source.schema_version ?? "—")],
            ["Checksums verified", p.checksums_verified != null ? formatNumber(p.checksums_verified) : null],
            ["Note", p.source.note],
          ]}
        />
      ) : null}
      {p?.counts ? (
        <div className="flex flex-wrap gap-2">
          {Object.entries(p.counts)
            .filter(([, n]) => n)
            .map(([k, n]) => (
              <Tag key={k}>
                {humanize(k)} {formatNumber(n)}
              </Tag>
            ))}
        </div>
      ) : null}
      {p?.warnings?.length ? (
        <ul className="list-disc pl-5 text-sm text-warning">
          {p.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      {ij.status === "validated" && p?.brands ? (
        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
          <Label>Where should each brand go?</Label>
          {p.brands.map((b) => (
            <div key={b.source_id} className="grid items-center gap-2 sm:grid-cols-[1fr_18rem]">
              <span className="text-base">
                {b.name}
                {b.conflict_brand_id ? <span className="ml-2 text-sm text-warning">a brand with this address already exists</span> : null}
              </span>
              <NativeSelect
                aria-label={`Target for ${b.name}`}
                value={mapping[b.source_id] ?? (b.conflict_brand_id ? `merge:${b.conflict_brand_id}` : "create")}
                onChange={(e) => setMapping((m) => ({ ...m, [b.source_id]: e.target.value }))}
              >
                <option value="create">Create as a new brand</option>
                {brands.data?.items.map((t) => (
                  <option key={t.id} value={`merge:${t.id}`}>
                    Merge into {t.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ))}
          {p.duplicates?.assets ? (
            <p className="text-sm text-muted">{p.duplicates.assets} asset(s) already exist here (same checksum).</p>
          ) : null}
          <div className="grid gap-1.5">
            {(
              [
                ["skip_duplicate_assets", "Skip assets that already exist (same checksum)"],
                ["import_ai_knowledge", "Import AI analysis records"],
                ["preserve_approvals", "Keep approval status from the source (otherwise everything arrives as draft)"],
                ["regenerate_embeddings", "Regenerate embeddings with this installation's model"],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-base">
                <Checkbox checked={opts[k]} onCheckedChange={(v) => setOpts((s) => ({ ...s, [k]: !!v }))} /> {label}
              </label>
            ))}
          </div>
        </div>
      ) : null}
      {ij.status === "committed" && report?.created ? (
        <div className="grid gap-2">
          <p className="font-medium text-accent">Imported</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(report.created).map(([k, n]) => (
              <Tag key={k} tone="accent">
                {humanize(k)} {n}
              </Tag>
            ))}
            {Object.entries(report.skipped ?? {}).map(([k, n]) => (
              <Tag key={k}>
                skipped {humanize(k)} {n}
              </Tag>
            ))}
          </div>
        </div>
      ) : null}
      {ij.status === "failed" && report?.errors?.length ? <ErrorState error={new Error(report.errors.join("; "))} /> : null}
      <div className="flex flex-wrap justify-end gap-2">
        {!["committing", "committed", "discarded"].includes(ij.status) ? (
          <Button variant="danger-outline" onClick={() => discard.mutate()} disabled={discard.isPending}>
            <Trash2 /> Discard
          </Button>
        ) : null}
        {ij.status === "validated" ? (
          <Button
            variant="primary"
            disabled={commit.isPending}
            onClick={async () => {
              if (
                await confirm({
                  title: "Commit this import?",
                  description: "Records are re-keyed into this workspace in one transaction. If anything fails, nothing is written.",
                  confirmLabel: "Commit import",
                })
              )
                commit.mutate();
            }}
          >
            Commit import
          </Button>
        ) : null}
      </div>
    </Panel>
  );
}
