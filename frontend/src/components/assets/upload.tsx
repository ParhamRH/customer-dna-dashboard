"use client";
import * as React from "react";
import { useOnChange } from "@/lib/state";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, Copy, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { ApiError, upload, errorMessage } from "@/lib/api";
import type { AssetDetail } from "@/lib/types";
import { ASSET_TYPE_LABELS, REFERENCE_ROLE_LABELS } from "@/lib/labels";
import { cn, formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";

type Item = {
  key: string;
  file: File;
  state: "queued" | "uploading" | "done" | "duplicate" | "error";
  progress: number;
  error?: string;
  existingId?: string;
  assetId?: string;
};

const ROLE_HINT: Record<string, string> = {
  official: "The brand's own approved-for-use material",
  inspiration: "External material that inspires the direction, never used as-is",
  historical: "Past work kept for reference",
  external: "Third-party references (provenance is recorded)",
  work_in_progress: "Unfinished drafts",
};

export function UploadDialog({ open, onOpenChange, defaults }: { open: boolean; onOpenChange: (o: boolean) => void; defaults?: { asset_type?: string } }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [items, setItems] = React.useState<Item[]>([]);
  const [meta, setMeta] = React.useState({ reference_role: "official", asset_type: defaults?.asset_type ?? "", category: "", tags: "", folder_path: "", license: "" });
  const [dragging, setDragging] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  useOnChange(open, () => {
    if (!open) {
      setItems([]);
      setRunning(false);
    }
  });

  const add = (files: FileList | File[]) =>
    setItems((xs) => [...xs, ...Array.from(files).map((f) => ({ key: `${f.name}-${f.size}-${Math.random()}`, file: f, state: "queued" as const, progress: 0 }))]);

  const patch = (key: string, p: Partial<Item>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x)));

  async function send(it: Item, allowDuplicate = false) {
    const form = new FormData();
    form.append("file", it.file);
    Object.entries(meta).forEach(([k, v]) => {
      if (!v) return;
      if (k === "license") form.append("license", JSON.stringify({ license: v }));
      else form.append(k, v);
    });
    if (allowDuplicate) form.append("allow_duplicate", "true");
    patch(it.key, { state: "uploading", progress: 0, error: undefined });
    try {
      const a = await upload<AssetDetail>(`/v1/brands/${ws.brand.id}/assets`, form, { org: ws.orgId, onProgress: (p) => patch(it.key, { progress: p }) });
      patch(it.key, { state: "done", progress: 1, assetId: a.id });
    } catch (e) {
      if (e instanceof ApiError && e.code === "duplicate_asset") {
        patch(it.key, { state: "duplicate", existingId: (e.details as { existing_asset_id?: string })?.existing_asset_id, error: e.message });
      } else patch(it.key, { state: "error", error: errorMessage(e) });
    }
  }

  async function startAll() {
    setRunning(true);
    const queue = items.filter((x) => x.state === "queued" || x.state === "error");
    // two at a time: fast enough, gentle on the API
    let i = 0;
    await Promise.all(
      [0, 1].map(async () => {
        while (i < queue.length) {
          const it = queue[i++];
          await send(it);
        }
      }),
    );
    setRunning(false);
    qc.invalidateQueries({ queryKey: ws.key("assets") });
    qc.invalidateQueries({ queryKey: ws.key("brand") });
  }

  const done = items.filter((x) => x.state === "done").length;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader
          title="Upload to the asset library"
          description="Originals are stored unchanged and checksummed. Previews, media analysis and AI interpretation run in the background; AI output waits for review."
        />
        <DialogBody className="grid gap-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (e.dataTransfer.files.length) add(e.dataTransfer.files);
            }}
            className={cn("grid place-items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors", dragging ? "border-accent bg-accent-soft" : "border-line-strong")}
          >
            <UploadCloud className="size-7 text-faint" />
            <p className="text-md">Drop images, video, PDFs, presentations, 3D models or documents here</p>
            <input ref={inputRef} type="file" multiple className="hidden" onChange={(e) => e.target.files && add(e.target.files)} data-testid="upload-input" />
            <Button size="sm" onClick={() => inputRef.current?.click()}>
              Choose files
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Reference role" htmlFor="u-role" hint={ROLE_HINT[meta.reference_role]}>
              <NativeSelect id="u-role" value={meta.reference_role} onChange={(e) => setMeta({ ...meta, reference_role: e.target.value })}>
                {Object.entries(REFERENCE_ROLE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Type" htmlFor="u-type" hint="Detected from the file when left on automatic.">
              <NativeSelect id="u-type" value={meta.asset_type} onChange={(e) => setMeta({ ...meta, asset_type: e.target.value })}>
                <option value="">Automatic</option>
                {Object.entries(ASSET_TYPE_LABELS)
                  .filter(([k]) => k !== "external_reference")
                  .map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
              </NativeSelect>
            </Field>
            <Field label="Category" htmlFor="u-cat">
              <Input id="u-cat" placeholder="e.g. photography" value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })} />
            </Field>
            <Field label="Tags" htmlFor="u-tags" hint="Comma separated">
              <Input id="u-tags" value={meta.tags} onChange={(e) => setMeta({ ...meta, tags: e.target.value })} />
            </Field>
            <Field label="Folder" htmlFor="u-folder">
              <Input id="u-folder" placeholder="/campaigns/2027" value={meta.folder_path} onChange={(e) => setMeta({ ...meta, folder_path: e.target.value })} />
            </Field>
            <Field label="License" htmlFor="u-lic">
              <Input id="u-lic" placeholder="e.g. Owned, CC BY 4.0" value={meta.license} onChange={(e) => setMeta({ ...meta, license: e.target.value })} />
            </Field>
          </div>
          {items.length ? (
            <ul className="grid max-h-64 gap-1 overflow-y-auto rounded-md border border-line p-1">
              {items.map((it) => (
                <li key={it.key} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-surface-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {it.state === "done" ? <CheckCircle2 className="size-4 text-accent" /> : it.state === "error" ? <CircleAlert className="size-4 text-danger" /> : it.state === "duplicate" ? <Copy className="size-4 text-warning" /> : null}
                      <span className="truncate">{it.file.name}</span>
                      <span className="shrink-0 text-muted">{formatBytes(it.file.size)}</span>
                    </div>
                    {it.state === "uploading" ? (
                      <div className="mt-1 h-1 overflow-hidden rounded-full bg-sunken">
                        <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(it.progress * 100)}%` }} />
                      </div>
                    ) : null}
                    {it.error ? <p className={it.state === "duplicate" ? "text-warning" : "text-danger"}>{it.error}</p> : null}
                  </div>
                  <div className="flex items-center gap-1">
                    {it.state === "done" && it.assetId ? (
                      <Link href={`${ws.base}/assets/${it.assetId}`} className="text-accent hover:underline">
                        Open
                      </Link>
                    ) : null}
                    {it.state === "duplicate" ? (
                      <>
                        {it.existingId ? (
                          <Link href={`${ws.base}/assets/${it.existingId}`} className="text-accent hover:underline">
                            View existing
                          </Link>
                        ) : null}
                        <Button size="sm" variant="ghost" onClick={() => send(it, true)}>
                          Upload anyway
                        </Button>
                      </>
                    ) : null}
                    {it.state === "queued" || it.state === "error" ? (
                      <Button size="icon-sm" variant="ghost" aria-label={`Remove ${it.file.name}`} onClick={() => setItems((xs) => xs.filter((x) => x.key !== it.key))}>
                        <X />
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <span className="mr-auto text-sm text-muted">{items.length ? `${done} of ${items.length} uploaded` : ""}</span>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Cancel"}
          </Button>
          <Button variant="primary" disabled={running || !items.some((x) => x.state === "queued" || x.state === "error")} onClick={startAll}>
            {running ? "Uploading…" : `Upload ${items.filter((x) => x.state === "queued" || x.state === "error").length || ""} file(s)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReferenceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const blank = { title: "", url: "", source_name: "", creator: "", license: "", notes: "", tags: "", reference_role: "external", description: "" };
  const [f, setF] = React.useState(blank);
  const create = useMutation({
    mutationFn: () =>
      ws.req<AssetDetail>(`/v1/brands/${ws.brand.id}/references`, {
        method: "POST",
        body: { ...f, tags: f.tags.split(",").map((x) => x.trim()).filter(Boolean), url: f.url || null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("assets") });
      toast.success("Reference recorded with its provenance");
      setF(blank);
      onOpenChange(false);
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader title="Record an external reference" description="For inspiration you link to rather than upload. Source, creator and license are kept as provenance." />
        <DialogBody className="grid gap-3 sm:grid-cols-2">
          <Field label="Title" htmlFor="r-title" className="sm:col-span-2">
            <Input id="r-title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label="URL" htmlFor="r-url" className="sm:col-span-2">
            <Input id="r-url" type="url" placeholder="https://" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
          </Field>
          <Field label="Source" htmlFor="r-src">
            <Input id="r-src" placeholder="Publication, museum, site" value={f.source_name} onChange={(e) => setF({ ...f, source_name: e.target.value })} />
          </Field>
          <Field label="Creator" htmlFor="r-cr">
            <Input id="r-cr" value={f.creator} onChange={(e) => setF({ ...f, creator: e.target.value })} />
          </Field>
          <Field label="License" htmlFor="r-lic">
            <Input id="r-lic" value={f.license} onChange={(e) => setF({ ...f, license: e.target.value })} />
          </Field>
          <Field label="Role" htmlFor="r-role">
            <NativeSelect id="r-role" value={f.reference_role} onChange={(e) => setF({ ...f, reference_role: e.target.value })}>
              {Object.entries(REFERENCE_ROLE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Why it matters" htmlFor="r-desc" className="sm:col-span-2">
            <Textarea id="r-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <Field label="Tags" htmlFor="r-tags" hint="Comma separated" className="sm:col-span-2">
            <Input id="r-tags" value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} />
          </Field>
          {create.error ? <p className="text-sm text-danger sm:col-span-2">{errorMessage(create.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.title || create.isPending} onClick={() => create.mutate()}>
            Record reference
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
