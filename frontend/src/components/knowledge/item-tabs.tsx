"use client";
import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useAssetPicker, useConcepts, useGuidelines, useMemberNames, usePrinciples, useProjects } from "@/lib/hooks";
import type { Relationship, Revision } from "@/lib/types";
import { ENTITY_LABELS, RELATION_LABELS } from "@/lib/labels";
import { formatDateTime, humanize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { AiTag, Status, Tag } from "@/components/status";
import { CodeBlock } from "@/components/code-block";
import { EmptyState, LoadingBlock } from "@/components/page";

/** Link to the page that shows a related entity. */
export function entityHref(base: string, type: string, id: string): string {
  switch (type) {
    case "asset":
      return `${base}/assets/${id}`;
    case "aesthetic_concept":
      return `${base}/aesthetics?concept=${id}`;
    case "principle":
      return `${base}/principles?item=principles:${id}`;
    case "guideline":
      return `${base}/principles?item=guidelines:${id}`;
    case "project":
      return `${base}/projects/${id}`;
    case "collection":
      return `${base}/collections/${id}`;
    default:
      return `${base}/graph?focus=${type}:${id}`;
  }
}

/* --------------------------------------------------------------------------------------------- */
const ADDABLE: Record<string, { relations: string[]; targets: string[] }> = {
  principle: { relations: ["applies_to", "related_to", "references"], targets: ["aesthetic_concept", "principle", "guideline", "project", "asset"] },
  guideline: { relations: ["supports", "related_to", "references", "applies_to"], targets: ["principle", "aesthetic_concept", "project", "asset"] },
  aesthetic_concept: { relations: ["related_to", "opposes", "broader_than"], targets: ["aesthetic_concept", "principle"] },
  knowledge_entry: { relations: ["related_to", "references", "supports"], targets: ["principle", "aesthetic_concept", "asset", "guideline"] },
  asset: { relations: ["exemplifies", "violates", "related_to", "references"], targets: ["aesthetic_concept", "principle", "guideline", "project"] },
  project: { relations: ["uses", "related_to"], targets: ["asset", "aesthetic_concept", "principle"] },
};

function TargetPicker({ type, value, onChange }: { type: string; value: string; onChange: (v: string) => void }) {
  const concepts = useConcepts();
  const principles = usePrinciples();
  const guidelines = useGuidelines();
  const projects = useProjects();
  const [q, setQ] = React.useState("");
  const assets = useAssetPicker(q, type === "asset");
  const options: { id: string; label: string }[] =
    type === "aesthetic_concept"
      ? (concepts.data?.items ?? []).map((c) => ({ id: c.id, label: c.name }))
      : type === "principle"
        ? (principles.data?.items ?? []).map((p) => ({ id: p.id, label: `${p.code} ${p.title}` }))
        : type === "guideline"
          ? (guidelines.data?.items ?? []).map((g) => ({ id: g.id, label: g.title }))
          : type === "project"
            ? (projects.data?.items ?? []).map((p) => ({ id: p.id, label: p.name }))
            : (assets.data?.items ?? []).map((a) => ({ id: a.id, label: a.title }));
  return (
    <div className="grid gap-1.5">
      {type === "asset" ? <Input placeholder="Search assets" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search assets" /> : null}
      <NativeSelect aria-label="Related item" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

export function RelationshipsTab({ entityType, entityId, relationships, canEdit }: { entityType: string; entityId: string; relationships: Relationship[]; canEdit: boolean }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const spec = ADDABLE[entityType] ?? ADDABLE.knowledge_entry;
  const [rel, setRel] = React.useState(spec.relations[0]);
  const [tType, setTType] = React.useState(spec.targets[0]);
  const [target, setTarget] = React.useState("");
  const invalidate = () => qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });
  const add = useMutation({
    mutationFn: () =>
      ws.req("/v1/relationships", {
        method: "POST",
        body: { source_type: entityType, source_id: entityId, relation_type: rel, target_type: tType, target_id: target },
      }),
    onSuccess: () => {
      toast.success("Relationship added");
      setTarget("");
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/relationships/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Relationship removed");
      invalidate();
    },
  });
  return (
    <div className="grid gap-5">
      {relationships.length === 0 ? (
        <EmptyState title="Not connected yet">Relationships link this item to example assets, concepts, principles and projects. Search and context packages follow them.</EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {relationships.map((r) => (
            <li key={r.id} className="flex items-center gap-3 px-3 py-2 text-base">
              <span className="w-28 shrink-0 text-sm text-muted">{r.direction === "outgoing" ? RELATION_LABELS[r.relation_type] : `← ${RELATION_LABELS[r.relation_type]}`}</span>
              <span className="min-w-0 flex-1">
                <Link href={entityHref(ws.base, r.other_type, r.other_id)} className="hover:underline">
                  {r.other_label ?? r.other_id}
                </Link>
                <span className="ml-2 text-sm text-muted">{ENTITY_LABELS[r.other_type] ?? humanize(r.other_type)}</span>
              </span>
              {r.status === "suggested" ? <AiTag label="Suggested" /> : r.origin === "ai_suggestion" ? <Tag tone="outline">from AI, accepted</Tag> : null}
              {canEdit ? (
                <Button size="icon-sm" variant="ghost" aria-label="Remove relationship" onClick={() => remove.mutate(r.id)}>
                  <Trash2 />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <div className="grid gap-2 rounded-md border border-dashed border-line-strong p-3">
          <p className="text-sm font-medium">Add a relationship</p>
          <div className="grid gap-2 sm:grid-cols-[10rem_10rem_1fr]">
            <NativeSelect aria-label="Relation" value={rel} onChange={(e) => setRel(e.target.value)}>
              {spec.relations.map((r) => (
                <option key={r} value={r}>
                  {RELATION_LABELS[r]}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Related type"
              value={tType}
              onChange={(e) => {
                setTType(e.target.value);
                setTarget("");
              }}
            >
              {spec.targets.map((t) => (
                <option key={t} value={t}>
                  {ENTITY_LABELS[t]}
                </option>
              ))}
            </NativeSelect>
            <TargetPicker type={tType} value={target} onChange={setTarget} />
          </div>
          <Button size="sm" className="justify-self-start" disabled={!target || add.isPending} onClick={() => add.mutate()}>
            <Plus /> Add relationship
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------------------------------------- */
const IGNORE = new Set(["status", "version", "updated_by", "approved_by", "approved_at", "id", "brand_id", "origin", "source_suggestion_id", "created_by", "slug", "code"]);

function changedFields(cur: Revision, prev?: Revision): string[] {
  if (!prev) return [];
  const keys = new Set([...Object.keys(cur.data ?? {}), ...Object.keys(prev.data ?? {})]);
  return [...keys].filter((k) => !IGNORE.has(k) && JSON.stringify(cur.data?.[k]) !== JSON.stringify(prev.data?.[k]));
}

export function HistoryTab({ collection, id }: { collection: string; id: string }) {
  const ws = useWorkspace();
  const name = useMemberNames();
  const q = useQuery({ queryKey: ws.key("revisions", collection, id), queryFn: () => ws.req<{ items: Revision[] }>(`/v1/knowledge/${collection}/${id}/revisions`) });
  const [open, setOpen] = React.useState<number | null>(null);
  if (!q.data) return <LoadingBlock rows={3} />;
  const items = q.data.items;
  return (
    <ol className="grid gap-0">
      {items.map((r, i) => {
        const changed = changedFields(r, items[i + 1]);
        return (
          <li key={r.version} className="relative border-l border-line pb-4 pl-5 last:pb-0">
            <span className={`absolute -left-[5px] top-1.5 size-2.5 rounded-full border-2 border-surface ${r.approved ? "bg-accent" : "bg-line-strong"}`} aria-hidden />
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-medium">Version {r.version}</span>
              {r.approved ? <Status status="approved" label={`Approved ${formatDateTime(r.approved_at)} by ${name(r.approved_by)}`} /> : null}
              <span className="text-sm text-muted">
                {formatDateTime(r.created_at)} · {name(r.created_by)}
              </span>
            </div>
            <p className="text-sm text-ink-2">
              {r.change_note || "edited"}
              {changed.length ? <span className="text-muted"> — changed {changed.map(humanize).join(", ").toLowerCase()}</span> : null}
            </p>
            <button className="text-sm text-accent hover:underline" onClick={() => setOpen(open === r.version ? null : r.version)}>
              {open === r.version ? "Hide content" : "Show content"}
            </button>
            {open === r.version ? <CodeBlock className="mt-2" code={JSON.stringify(r.data, null, 2)} label={`Version ${r.version}`} maxHeight="18rem" /> : null}
          </li>
        );
      })}
    </ol>
  );
}

/* --------------------------------------------------------------------------------------------- */
export function ExportTab({ collection, id, name }: { collection: string; id: string; name: string }) {
  const ws = useWorkspace();
  const [fmt, setFmt] = React.useState<"json" | "yaml">("yaml");
  const q = useQuery({
    queryKey: ws.key("item-export", collection, id, fmt),
    queryFn: async () => {
      const r = await ws.req<unknown>(`/v1/knowledge/${collection}/${id}/export`, { params: { format: fmt } });
      return typeof r === "string" ? r : JSON.stringify(r, null, 2);
    },
  });
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item";
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">Machine-readable record with its approved relationships — what AI tools receive.</p>
        <Segmented label="Format" value={fmt} onChange={setFmt} options={[{ value: "yaml", label: "YAML" }, { value: "json", label: "JSON" }]} />
      </div>
      {q.data ? (
        <CodeBlock code={q.data} filename={`${slug}.${fmt}`} mime={fmt === "json" ? "application/json" : "application/yaml"} />
      ) : (
        <LoadingBlock rows={4} />
      )}
    </div>
  );
}
