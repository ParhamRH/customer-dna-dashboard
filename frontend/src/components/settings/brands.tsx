"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { Brand } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Panel } from "@/components/page";
import { Status } from "@/components/status";
import { useConfirm } from "@/components/confirm";

export function BrandsPanel() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [edit, setEdit] = React.useState<Brand | "new" | null>(null);
  const can = ws.can("brand.manage");
  const reindex = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/brands/${id}/reindex`, { method: "POST" }),
    onSuccess: () => toast.success("Re-indexing queued. Search keeps working while it runs."),
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => ws.req(`/v1/brands/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ws.key("workspace") }),
  });
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-base text-ink-2">Each brand has its own library, knowledge, palettes and versions. Members see all brands in the workspace unless a token is restricted to one.</p>
        {can ? (
          <Button variant="primary" onClick={() => setEdit("new")}>
            <Plus /> New brand
          </Button>
        ) : null}
      </div>
      <Panel>
        <Table>
          <THead>
            <tr>
              <th>Brand</th>
              <th>Slug</th>
              <th>Language</th>
              <th>Created</th>
              <th>Status</th>
              <th className="w-0" />
            </tr>
          </THead>
          <TBody>
            {ws.brands.map((b) => (
              <tr key={b.id}>
                <td>
                  <Link href={`/w/${ws.orgSlug}/${b.slug}`} className="font-medium hover:underline">
                    {b.name}
                  </Link>
                  {b.tagline ? <div className="text-sm text-muted">{b.tagline}</div> : null}
                </td>
                <td className="font-mono text-[12px] text-muted">{b.slug}</td>
                <td className="text-sm">{b.primary_language}</td>
                <td className="whitespace-nowrap text-sm text-muted">{formatDate(b.created_at)}</td>
                <td>
                  <Status status={b.status === "active" ? "active" : "archived"} label={b.status === "active" ? "Active" : "Archived"} />
                </td>
                <td>
                  {can ? (
                    <div className="flex gap-1">
                      <Button size="sm" onClick={() => setEdit(b)}>
                        Edit
                      </Button>
                      <Button size="sm" variant="ghost" disabled={reindex.isPending} onClick={() => reindex.mutate(b.id)} title="Rebuild search embeddings">
                        Re-index
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          const archive = b.status === "active";
                          if (!archive || (await confirm({ title: `Archive ${b.name}?`, description: "The brand becomes read-only history. Nothing is deleted and you can reactivate it.", confirmLabel: "Archive brand" })))
                            setStatus.mutate({ id: b.id, status: archive ? "archived" : "active" });
                        }}
                      >
                        {b.status === "active" ? "Archive" : "Reactivate"}
                      </Button>
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </TBody>
        </Table>
      </Panel>
      <BrandDialog target={edit} onClose={() => setEdit(null)} />
    </div>
  );
}

function BrandDialog({ target, onClose }: { target: Brand | "new" | null; onClose: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const existing = target && target !== "new" ? target : null;
  const [f, setF] = useResetState([existing?.id ?? target], () =>
    existing
      ? { name: existing.name, slug: existing.slug, tagline: existing.tagline ?? "", description: existing.description ?? "", primary_language: existing.primary_language }
      : { name: "", slug: "", tagline: "", description: "", primary_language: "en" },
  );
  const save = useMutation({
    mutationFn: () => {
      const body = { name: f.name, tagline: f.tagline || null, description: f.description || null, primary_language: f.primary_language };
      return existing ? ws.req<Brand>(`/v1/brands/${existing.id}`, { method: "PATCH", body }) : ws.req<Brand>("/v1/brands", { method: "POST", body: { ...body, slug: f.slug || null } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("workspace") });
      toast.success(existing ? "Brand saved" : "Brand created");
      onClose();
    },
    onError: () => {},
  });
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader title={existing ? `Edit ${existing.name}` : "New brand"} description={existing ? undefined : "Starts empty. Add palettes, knowledge and assets from the brand’s own pages."} />
        <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <Field label="Name" htmlFor="br-name">
            <Input id="br-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus />
          </Field>
          {!existing ? (
            <Field label="URL slug" htmlFor="br-slug" hint="Optional — derived from the name. Cannot be changed later.">
              <Input id="br-slug" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} className="font-mono text-[13px]" />
            </Field>
          ) : null}
          <Field label="Tagline" htmlFor="br-tag">
            <Input id="br-tag" value={f.tagline} onChange={(e) => setF({ ...f, tagline: e.target.value })} />
          </Field>
          <Field label="Description" htmlFor="br-desc">
            <Textarea id="br-desc" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <Field label="Primary language" htmlFor="br-lang">
            <NativeSelect id="br-lang" value={f.primary_language} onChange={(e) => setF({ ...f, primary_language: e.target.value })} className="w-48">
              {[
                ["en", "English"],
                ["de", "German"],
                ["fr", "French"],
                ["es", "Spanish"],
                ["it", "Italian"],
                ["nl", "Dutch"],
                ["sv", "Swedish"],
                ["ja", "Japanese"],
              ].map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name.trim() || save.isPending} onClick={() => save.mutate()}>
            {existing ? "Save brand" : "Create brand"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
