"use client";
import * as React from "react";
import { useOnChange } from "@/lib/state";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useWorkspace } from "@/lib/workspace";
import { useConcepts, useMemberNames, usePrinciples, useRegistry } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { Concept, EntryType, Guideline, Json, KnowledgeEntry, Principle } from "@/lib/types";
import { CLASSIFICATIONS, PROJECT_TYPE_LABELS, RELEVANCE } from "@/lib/labels";
import { cn, formatDateTime, humanize } from "@/lib/utils";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { OriginNote, Status } from "@/components/status";
import { LoadingBlock } from "@/components/page";
import { useConfirm } from "@/components/confirm";
import { GovernanceActions, type Collection } from "./governance";
import { ExportTab, HistoryTab, RelationshipsTab } from "./item-tabs";
import { ListEditor, StructuredForm } from "./structured";
import { MarkdownEditor } from "./markdown-editor";

export type SheetTarget =
  | { collection: Collection; id: string }
  | { collection: Collection; create: true; defaults?: Json }
  | null;

const ETYPE: Record<Collection, string> = { entries: "knowledge_entry", principles: "principle", guidelines: "guideline", concepts: "aesthetic_concept" };
const WRITE_PERM: Record<Collection, string> = { entries: "knowledge.write", principles: "knowledge.write", guidelines: "knowledge.write", concepts: "concepts.manage" };
const NOUN: Record<Collection, string> = { entries: "entry", principles: "principle", guidelines: "guideline", concepts: "concept" };

type AnyItem = (KnowledgeEntry | Principle | Guideline | Concept) & Json;

function itemName(c: Collection, x: Json): string {
  return String((c === "concepts" ? x.name : x.title) ?? "");
}

/* --- per-type forms ------------------------------------------------------------------------- */
function EntryForm({ v, set, types, isNew }: { v: Json; set: (k: string, val: unknown) => void; types: EntryType[]; isNew: boolean }) {
  const t = types.find((x) => x.key === v.entry_type);
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Entry type" htmlFor="e-type">
          <NativeSelect id="e-type" value={String(v.entry_type ?? "")} onChange={(e) => set("entry_type", e.target.value)} disabled={!isNew && false}>
            {types.map((x) => (
              <option key={x.key} value={x.key}>
                {x.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Title" htmlFor="e-title">
          <Input id="e-title" value={String(v.title ?? "")} onChange={(e) => set("title", e.target.value)} />
        </Field>
      </div>
      <Field label="Summary" htmlFor="e-sum" hint="One or two sentences. Used in context packages and search results.">
        <Textarea id="e-sum" rows={2} className="font-serif text-md" value={String(v.summary ?? "")} onChange={(e) => set("summary", e.target.value)} />
      </Field>
      {t ? (
        <fieldset className="grid gap-3 rounded-md border border-line p-3">
          <legend className="px-1 text-sm font-medium text-muted">Structured fields</legend>
          <StructuredForm fields={t.fields} value={(v.structured as Json) ?? {}} onChange={(s) => set("structured", s)} />
        </fieldset>
      ) : null}
      <MarkdownEditor label="Document" value={String(v.body ?? "")} onChange={(b) => set("body", b)} />
      <Field label="Tags" htmlFor="e-tags" hint="Comma separated.">
        <Input
          id="e-tags"
          value={((v.tags as string[]) ?? []).join(", ")}
          onChange={(e) => set("tags", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))}
        />
      </Field>
    </div>
  );
}

function ProjectTypes({ value, onChange, label }: { value: string[]; onChange: (v: string[]) => void; label: string }) {
  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {Object.entries(PROJECT_TYPE_LABELS).map(([k, l]) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <Checkbox checked={value.includes(k)} onCheckedChange={() => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k])} />
            {l}
          </label>
        ))}
      </div>
    </div>
  );
}

function PrincipleForm({ v, set, domains }: { v: Json; set: (k: string, val: unknown) => void; domains: { key: string; name: string }[] }) {
  const scope = (v.scope as { project_types?: string[] }) ?? {};
  const ex = (v.examples as { do?: string[]; dont?: string[] }) ?? {};
  return (
    <div className="grid gap-4">
      <Field label="Title" htmlFor="p-title">
        <Input id="p-title" value={String(v.title ?? "")} onChange={(e) => set("title", e.target.value)} />
      </Field>
      <Field label="Statement" htmlFor="p-stmt" hint="The rule itself, stated plainly.">
        <Textarea id="p-stmt" rows={3} className="font-serif text-lg" value={String(v.statement ?? "")} onChange={(e) => set("statement", e.target.value)} />
      </Field>
      <Field label="Rationale" htmlFor="p-rat" hint="Why the brand works this way.">
        <Textarea id="p-rat" rows={2} value={String(v.rationale ?? "")} onChange={(e) => set("rationale", e.target.value)} />
      </Field>
      <div className="grid gap-1.5">
        <Label>Classification</Label>
        <div role="radiogroup" aria-label="Classification" className="grid gap-1.5 sm:grid-cols-2">
          {CLASSIFICATIONS.map((c) => (
            <label key={c.key} className={cn("flex cursor-pointer items-start gap-2 rounded-md border px-2.5 py-2 text-base", v.classification === c.key ? "border-ink bg-surface-2" : "border-line hover:bg-surface-2")}>
              <input type="radio" name="classification" className="mt-1 accent-[var(--accent)]" checked={v.classification === c.key} onChange={() => set("classification", c.key)} />
              <span>
                <span className="font-medium">{c.label}</span>
                <span className="block text-sm text-muted">{c.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Domain" htmlFor="p-domain">
          <NativeSelect id="p-domain" value={String(v.domain_key ?? "")} onChange={(e) => set("domain_key", e.target.value || null)}>
            <option value="">Brand-wide</option>
            {domains.map((d) => (
              <option key={d.key} value={d.key}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Priority" htmlFor="p-prio" hint="0 = most important. Orders principles in context packages.">
          <Input id="p-prio" type="number" min={0} max={100} value={Number(v.priority ?? 50)} onChange={(e) => set("priority", Number(e.target.value))} />
        </Field>
      </div>
      <ProjectTypes label="Applies to project types (empty = all work)" value={scope.project_types ?? []} onChange={(pt) => set("scope", { ...scope, project_types: pt })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>Do</Label>
          <ListEditor label="Do" value={ex.do ?? []} onChange={(d) => set("examples", { ...ex, do: d.filter((x) => x.trim()) })} />
        </div>
        <div className="grid gap-1.5">
          <Label>Don&apos;t</Label>
          <ListEditor label="Don't" value={ex.dont ?? []} onChange={(d) => set("examples", { ...ex, dont: d.filter((x) => x.trim()) })} />
        </div>
      </div>
    </div>
  );
}

function GuidelineForm({ v, set, domains, isNew }: { v: Json; set: (k: string, val: unknown) => void; domains: { key: string; name: string }[]; isNew: boolean }) {
  const principles = usePrinciples();
  const applies = (v.applies_to as { project_types?: string[] }) ?? {};
  const pids = (v.principle_ids as string[]) ?? [];
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Title" htmlFor="g-title">
          <Input id="g-title" value={String(v.title ?? "")} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label="Domain" htmlFor="g-domain">
          <NativeSelect id="g-domain" value={String(v.domain_key ?? "")} onChange={(e) => set("domain_key", e.target.value)}>
            {domains.map((d) => (
              <option key={d.key} value={d.key}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <Field label="Summary" htmlFor="g-sum">
        <Textarea id="g-sum" rows={2} value={String(v.summary ?? "")} onChange={(e) => set("summary", e.target.value)} />
      </Field>
      <MarkdownEditor label="Guideline document" rows={12} value={String(v.body ?? "")} onChange={(b) => set("body", b)} />
      <ProjectTypes label="Relevant for project types" value={applies.project_types ?? []} onChange={(pt) => set("applies_to", { ...applies, project_types: pt })} />
      {isNew && principles.data?.items.length ? (
        <div className="grid gap-1.5">
          <Label>Supports principles</Label>
          <div className="grid max-h-40 gap-1 overflow-y-auto rounded-md border border-line p-2">
            {principles.data.items.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-sm">
                <Checkbox checked={pids.includes(p.id)} onCheckedChange={() => set("principle_ids", pids.includes(p.id) ? pids.filter((x) => x !== p.id) : [...pids, p.id])} />
                <span className="font-mono text-[11px] text-muted">{p.code}</span> {p.title}
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ConceptMulti({ label, value, onChange, exclude }: { label: string; value: string[]; onChange: (v: string[]) => void; exclude?: string }) {
  const concepts = useConcepts();
  const items = (concepts.data?.items ?? []).filter((c) => c.id !== exclude);
  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {items.map((c) => {
          const on = value.includes(c.id);
          return (
            <button
              type="button"
              key={c.id}
              aria-pressed={on}
              onClick={() => onChange(on ? value.filter((x) => x !== c.id) : [...value, c.id])}
              className={cn("h-6 rounded-full border px-2.5 text-sm transition-colors", on ? "border-ink bg-ink text-paper" : "border-line-strong text-ink-2 hover:bg-sunken")}
            >
              {c.name}
            </button>
          );
        })}
        {!items.length ? <span className="text-sm text-muted">No other concepts yet.</span> : null}
      </div>
    </div>
  );
}

function ConceptForm({ v, set, id }: { v: Json; set: (k: string, val: unknown) => void; id?: string }) {
  return (
    <div className="grid gap-4">
      <Field label="Name" htmlFor="c-name">
        <Input id="c-name" value={String(v.name ?? "")} onChange={(e) => set("name", e.target.value)} />
      </Field>
      <Field label="Definition" htmlFor="c-def" hint="What the concept means for this brand, precisely enough that a designer or a model can apply it.">
        <Textarea id="c-def" rows={3} className="font-serif text-lg" value={String(v.definition ?? "")} onChange={(e) => set("definition", e.target.value)} />
      </Field>
      <div className="grid gap-1.5">
        <Label>Brand relevance</Label>
        <div role="radiogroup" aria-label="Brand relevance" className="flex flex-wrap gap-1.5">
          {RELEVANCE.map((r) => (
            <label key={r.key} title={r.hint} className={cn("flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm", v.brand_relevance === r.key ? "border-ink bg-surface-2 font-medium" : "border-line")}>
              <input type="radio" name="relevance" className="accent-[var(--accent)]" checked={v.brand_relevance === r.key} onChange={() => set("brand_relevance", r.key)} />
              {r.label}
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>Synonyms</Label>
          <ListEditor label="Synonyms" value={(v.synonyms as string[]) ?? []} onChange={(s) => set("synonyms", s.filter((x) => x.trim()))} />
        </div>
        <div className="grid gap-1.5">
          <Label>Attributes</Label>
          <ListEditor label="Attributes" placeholder="e.g. soft edges" value={((v.attributes as unknown[]) ?? []).map(String)} onChange={(s) => set("attributes", s.filter((x) => x.trim()))} />
        </div>
      </div>
      <ConceptMulti label="Related concepts" exclude={id} value={(v.related_concept_ids as string[]) ?? []} onChange={(x) => set("related_concept_ids", x)} />
      <ConceptMulti label="Opposing concepts" exclude={id} value={(v.opposing_concept_ids as string[]) ?? []} onChange={(x) => set("opposing_concept_ids", x)} />
      <ConceptMulti label="Broader concepts (this one is a kind of…)" exclude={id} value={(v.broader_concept_ids as string[]) ?? []} onChange={(x) => set("broader_concept_ids", x)} />
    </div>
  );
}

/* --- the sheet -------------------------------------------------------------------------------- */
const FIELDS: Record<Collection, string[]> = {
  entries: ["domain_key", "entry_type", "title", "summary", "body", "structured", "tags", "sort_order"],
  principles: ["title", "statement", "rationale", "classification", "domain_key", "scope", "examples", "priority"],
  guidelines: ["title", "domain_key", "summary", "body", "applies_to"],
  concepts: ["name", "definition", "attributes", "synonyms", "brand_relevance", "relevance_score", "related_concept_ids", "opposing_concept_ids", "broader_concept_ids"],
};

function initialFromItem(c: Collection, item: AnyItem): Json {
  const v: Json = {};
  for (const k of FIELDS[c]) if (k in item) v[k] = item[k];
  if (c === "concepts") {
    const ci = item as unknown as Concept;
    v.related_concept_ids = (ci.related_concepts ?? []).map((r) => r.other_id);
    v.opposing_concept_ids = (ci.opposing_concepts ?? []).map((r) => r.other_id);
    v.broader_concept_ids = (ci.broader_concepts ?? []).map((r) => r.other_id);
  }
  return v;
}

const CREATE_DEFAULTS: Record<Collection, Json> = {
  entries: { title: "", summary: "", body: "", structured: {}, tags: [] },
  principles: { title: "", statement: "", rationale: "", classification: "preferred", priority: 50, scope: {}, examples: {} },
  guidelines: { title: "", summary: "", body: "", applies_to: {}, principle_ids: [] },
  concepts: { name: "", definition: "", brand_relevance: "supporting", synonyms: [], attributes: [] },
};

export function KnowledgeSheet({ target, onClose }: { target: SheetTarget; onClose: () => void }) {
  return (
    <Dialog open={!!target} onOpenChange={(o) => !o && onClose()}>
      {target ? (
        <SheetContent width="w-[min(760px,100vw)]" aria-describedby={undefined}>
          <SheetBody key={"id" in target ? target.id : "new"} target={target} onClose={onClose} />
        </SheetContent>
      ) : null}
    </Dialog>
  );
}

function SheetBody({ target, onClose }: { target: NonNullable<SheetTarget>; onClose: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const registry = useRegistry();
  const name = useMemberNames();
  const c = target.collection;
  const isNew = "create" in target;
  const id = "id" in target ? target.id : undefined;
  const item = useQuery({
    queryKey: ws.key("item", c, id),
    queryFn: () => ws.req<AnyItem>(`/v1/knowledge/${c}/${id}`),
    enabled: !!id,
  });
  const [form, setForm] = React.useState<Json | null>(isNew ? { ...CREATE_DEFAULTS[c], ...(("defaults" in target && target.defaults) || {}) } : null);
  const [note, setNote] = React.useState("");
  const [tab, setTab] = React.useState("content");
  // Load the record into the form when it arrives (and again after a save refetches it).
  useOnChange(item.data, () => {
    if (item.data && !isNew) setForm(initialFromItem(c, item.data));
  });

  const domains = (registry.data?.domains ?? []).filter((d) => !["creative_assets", "ai_knowledge"].includes(d.key));
  const entryTypes = form?.domain_key ? registry.data?.entry_types[String(form.domain_key)] ?? [] : [];
  // New records default to the first entry type / domain once the registry has loaded.
  if (c === "entries" && isNew && form && !form.entry_type && entryTypes.length) setForm({ ...form, entry_type: entryTypes[0].key });
  if (c === "guidelines" && isNew && form && !form.domain_key && domains.length) setForm({ ...form, domain_key: domains[0].key });

  const canWrite = ws.can(WRITE_PERM[c]);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });

  const save = useMutation({
    mutationFn: async (opts: { submit?: boolean }) => {
      if (!form) return null;
      if (isNew) {
        return ws.req<AnyItem>(`/v1/brands/${ws.brand.id}/knowledge/${c}`, { method: "POST", body: form, params: { submit: opts.submit || undefined } });
      }
      const original = initialFromItem(c, item.data!);
      const changes: Json = {};
      for (const k of Object.keys(form)) if (JSON.stringify(form[k]) !== JSON.stringify(original[k])) changes[k] = form[k];
      if (!Object.keys(changes).length) return item.data!;
      return ws.req<AnyItem>(`/v1/knowledge/${c}/${id}`, { method: "PATCH", body: { ...changes, change_note: note || undefined } });
    },
    onSuccess: (r) => {
      invalidate();
      setNote("");
      if (isNew) {
        toast.success(`${humanize(NOUN[c])} created as ${r?.status === "in_review" ? "submitted for review" : "draft"}`);
        onClose();
      } else toast.success(item.data?.status === "approved" ? "Saved as a new draft version. The approved version stays official until this one is approved." : "Changes saved");
    },
    onError: () => {},
  });
  const del = useMutation({
    mutationFn: () => ws.req(`/v1/knowledge/${c}/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Deleted");
      onClose();
    },
  });

  if (!isNew && !item.data) return <div className="p-6"><LoadingBlock rows={6} /></div>;
  if (!form) return <div className="p-6"><LoadingBlock rows={6} /></div>;
  const x = item.data;
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f!, [k]: v }));
  const official = x?.has_official_version && x.status !== "approved";
  const title = isNew ? `New ${NOUN[c]}` : itemName(c, x as Json);
  const valid =
    c === "entries" ? !!form.title && !!form.entry_type : c === "principles" ? !!form.title && !!form.statement : c === "guidelines" ? !!form.title && !!form.domain_key : !!form.name && !!form.definition;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 pb-3 pt-5 pr-12">
        <DialogPrimitive.Title className="text-xl font-semibold">{title || "Untitled"}</DialogPrimitive.Title>
        {x ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <Status status={x.status} />
            <span>Version {x.version}</span>
            {x.status === "approved" ? <span>Approved {formatDateTime(x.approved_at)} by {name(x.approved_by)}</span> : null}
            {official ? <span className="text-ink-2">Official version: v{x.official_version} (this draft is not yet official)</span> : null}
            {"code" in x && x.code ? <span className="font-mono text-xs">{String(x.code)}</span> : null}
            <OriginNote origin={x.origin} />
          </div>
        ) : (
          <p className="mt-1 text-sm text-muted">Starts as a draft. It becomes official brand knowledge only when someone with approval rights approves it.</p>
        )}
      </div>
      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        {!isNew ? (
          <TabsList className="px-6 pt-2">
            <TabsTrigger value="content">Content</TabsTrigger>
            <TabsTrigger value="relationships">Relationships {x?.relationships?.length ? <span className="text-faint">{x.relationships.length}</span> : null}</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="export">JSON / YAML</TabsTrigger>
          </TabsList>
        ) : null}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
          <TabsContent value="content">
            <fieldset disabled={!canWrite} className="contents">
              {c === "entries" ? (
                <EntryForm v={form} set={set} types={entryTypes} isNew={isNew} />
              ) : c === "principles" ? (
                <PrincipleForm v={form} set={set} domains={domains} />
              ) : c === "guidelines" ? (
                <GuidelineForm v={form} set={set} domains={domains} isNew={isNew} />
              ) : (
                <ConceptForm v={form} set={set} id={id} />
              )}
            </fieldset>
          </TabsContent>
          {!isNew && x ? (
            <>
              <TabsContent value="relationships">
                <RelationshipsTab entityType={ETYPE[c]} entityId={x.id} relationships={x.relationships ?? []} canEdit={ws.can("knowledge.write")} />
              </TabsContent>
              <TabsContent value="history">
                <HistoryTab collection={c} id={x.id} />
              </TabsContent>
              <TabsContent value="export">
                <ExportTab collection={c} id={x.id} name={title} />
              </TabsContent>
            </>
          ) : null}
        </div>
      </Tabs>
      <div className="grid gap-2 border-t border-line bg-surface-2 px-6 py-3">
        {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        <div className="flex flex-wrap items-center gap-2">
          {x ? (
            <GovernanceActions collection={c} id={x.id} status={x.status} canApprove={!!x.can_approve} writePerm={WRITE_PERM[c]} />
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            {x && canWrite && tab === "content" && !["approved", "deprecated", "archived"].includes(x.status) && !x.has_official_version ? (
              <Button
                size="sm"
                variant="ghost"
                aria-label="Delete"
                onClick={async () => {
                  if (await confirm({ title: `Delete “${title}”?`, description: "Drafts that were never approved can be deleted. This cannot be undone.", confirmLabel: "Delete", destructive: true }))
                    del.mutate();
                }}
              >
                <Trash2 />
              </Button>
            ) : null}
            {canWrite && tab === "content" ? (
              <>
                {!isNew ? <Input className="h-7 w-56 text-sm" placeholder="What changed? (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Change note" /> : null}
                {isNew ? (
                  <Button size="sm" variant="ghost" disabled={!valid || save.isPending} onClick={() => save.mutate({ submit: true })}>
                    Create and submit
                  </Button>
                ) : null}
                <Button size="sm" variant="primary" disabled={!valid || save.isPending} onClick={() => save.mutate({})}>
                  {save.isPending ? "Saving…" : isNew ? "Create draft" : x?.status === "approved" ? "Save as new draft" : "Save changes"}
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
