"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useConcepts, useMemberNames, useReviewSummary } from "@/lib/hooks";
import type { Analysis, Interpretation, Json, Page, Suggestion } from "@/lib/types";
import { CLASSIFICATIONS, ENTITY_LABELS, KNOWLEDGE_STATUS_LABELS, RELATION_LABELS } from "@/lib/labels";
import { cn, formatDateTime, humanize, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Kbd, TBody, THead, Table } from "@/components/ui/misc";
import { AiTag, ClassificationTag, Status, Tag } from "@/components/status";
import { AssetThumb } from "@/components/asset-thumb";
import { AnalysisMeta, InterpretationView, ObjectiveView } from "@/components/assets/analysis";

/* ------------------------------------------------------------------------------------------ */
function csv(v: string): string[] {
  return v.split(",").map((x) => x.trim()).filter(Boolean);
}

function InterpretationEditor({ value, onChange }: { value: Interpretation; onChange: (v: Interpretation) => void }) {
  const concepts = useConcepts();
  const names = (concepts.data?.items ?? []).map((c) => c.name);
  const set = (k: keyof Interpretation, v: unknown) => onChange({ ...value, [k]: v });
  return (
    <div className="grid gap-3">
      <Field label="Summary" htmlFor="ie-sum">
        <Textarea id="ie-sum" rows={2} value={value.summary ?? ""} onChange={(e) => set("summary", e.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Atmosphere" htmlFor="ie-atm" hint="Comma separated">
          <Input id="ie-atm" value={(value.atmosphere ?? []).join(", ")} onChange={(e) => set("atmosphere", csv(e.target.value))} />
        </Field>
        <Field label="Visual style" htmlFor="ie-vs" hint="Comma separated">
          <Input id="ie-vs" value={(value.visual_style ?? []).join(", ")} onChange={(e) => set("visual_style", csv(e.target.value))} />
        </Field>
      </div>
      <div className="grid gap-1.5">
        <span className="text-sm font-medium text-ink-2">Aesthetic concepts</span>
        <div className="flex flex-wrap gap-1.5">
          {(value.aesthetic_concepts ?? []).map((c) => (
            <Tag key={c.name} className="pr-0.5">
              {c.name}
              <button aria-label={`Remove ${c.name}`} className="rounded p-0.5 hover:bg-line" onClick={() => set("aesthetic_concepts", (value.aesthetic_concepts ?? []).filter((x) => x.name !== c.name))}>
                <X className="size-3" />
              </button>
            </Tag>
          ))}
          <NativeSelect
            aria-label="Add concept"
            className="h-6 w-44 text-xs"
            value=""
            onChange={(e) => e.target.value && set("aesthetic_concepts", [...(value.aesthetic_concepts ?? []), { name: e.target.value, confidence: 1, evidence: "added by reviewer" }])}
          >
            <option value="">Add a concept…</option>
            {names.filter((n) => !(value.aesthetic_concepts ?? []).some((c) => c.name === n)).map((n) => (
              <option key={n}>{n}</option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <Field label="Possible applications" htmlFor="ie-app" hint="Comma separated">
        <Input id="ie-app" value={(value.potential_applications ?? []).join(", ")} onChange={(e) => set("potential_applications", csv(e.target.value))} />
      </Field>
    </div>
  );
}

function AnalysisReview({ a, onDecided }: { a: Analysis; onDecided: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const [interp, setInterp] = React.useState<Interpretation>(a.interpretive);
  const [notes, setNotes] = React.useState("");
  const [relevance, setRelevance] = React.useState("");
  const [tags, setTags] = React.useState(true);
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      ws.req(`/v1/review/analyses/${a.id}`, {
        method: "POST",
        body: {
          decision,
          notes: notes || null,
          interpretive: decision === "approve" && editing ? interp : null,
          brand_relevance: relevance || null,
          accept_suggested_tags: decision === "approve" && tags,
        },
      }),
    onSuccess: (_d, decision) => {
      toast.success(decision === "approve" ? (editing ? "Accepted with your edits" : "Interpretation accepted") : "Interpretation rejected");
      qc.invalidateQueries({ queryKey: ws.key("review") });
      qc.invalidateQueries({ queryKey: ws.key("assets") });
      onDecided();
    },
  });
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (editing || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey) return;
      if (e.key === "a") decide.mutate("approve");
      if (e.key === "r") decide.mutate("reject");
      if (e.key === "e") setEditing(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [decide, editing]);
  const asset = a.asset;
  return (
    <div className="grid gap-5">
      {asset ? (
        <div className="grid gap-4 sm:grid-cols-[14rem_1fr]">
          <Link href={`${ws.base}/assets/${asset.id}`}>
            <AssetThumb asset={asset} size="preview" fit="contain" className="aspect-[4/3] rounded-md" />
          </Link>
          <div className="min-w-0">
            <Link href={`${ws.base}/assets/${asset.id}`} className="text-lg font-semibold hover:underline">
              {asset.title}
            </Link>
            <p className="text-sm text-muted">
              {humanize(asset.asset_type)} · {humanize(asset.reference_role)} · asset {KNOWLEDGE_STATUS_LABELS[asset.approval_status]?.toLowerCase()}
            </p>
            <div className="mt-3">
              <AnalysisMeta a={a} />
            </div>
          </div>
        </div>
      ) : (
        <AnalysisMeta a={a} />
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <p className="mb-1.5 text-sm font-medium">Measured</p>
          <ObjectiveView data={a.objective} />
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-sm font-medium">Interpretation</p>
            {!editing ? (
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                <Pencil /> Edit before accepting
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setInterp(a.interpretive); }}>
                Discard edits
              </Button>
            )}
          </div>
          {editing ? <InterpretationEditor value={interp} onChange={setInterp} /> : <InterpretationView x={interp} />}
        </div>
      </div>
      <Panel className="grid gap-3 bg-surface-2 p-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_16rem]">
          <Input placeholder="Note for the decision history (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Review note" />
          <NativeSelect aria-label="Brand relevance" value={relevance} onChange={(e) => setRelevance(e.target.value)}>
            <option value="">Brand relevance: as the AI read it</option>
            {["core", "supporting", "peripheral", "off_brand"].map((r) => (
              <option key={r} value={r}>
                Brand relevance: {humanize(r).toLowerCase()}
              </option>
            ))}
          </NativeSelect>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={tags} onCheckedChange={(v) => setTags(!!v)} /> Also apply the suggested tags
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" disabled={decide.isPending} onClick={() => decide.mutate("approve")}>
            <Check /> {editing ? "Accept with edits" : "Accept interpretation"}
          </Button>
          <Button disabled={decide.isPending} onClick={() => decide.mutate("reject")}>
            <X /> Reject
          </Button>
          <span className="ml-auto hidden items-center gap-1.5 text-xs text-muted sm:flex">
            <Kbd>a</Kbd> accept <Kbd>r</Kbd> reject <Kbd>e</Kbd> edit <Kbd>j</Kbd>/<Kbd>k</Kbd> next / previous
          </span>
        </div>
        <p className="text-xs text-muted">Accepting links this reading to the asset for search and context. It never changes approved principles or other official knowledge.</p>
      </Panel>
    </div>
  );
}

function InterpretationsTab() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const assetFilter = params.get("asset");
  const q = useQuery({
    queryKey: ws.key("review", "analyses", ws.brand.id, assetFilter),
    queryFn: () => ws.req<Page<Analysis>>("/v1/review/analyses", { params: { brand_id: ws.brand.id, asset_id: assetFilter, limit: 100 } }),
  });
  const [current, setCurrent] = React.useState<string | null>(null);
  const items = React.useMemo(() => q.data?.items ?? [], [q.data]);
  const idx = Math.max(0, items.findIndex((x) => x.id === current));
  const sel = items[idx];
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.key === "j" && items[idx + 1]) setCurrent(items[idx + 1].id);
      if (e.key === "k" && items[idx - 1]) setCurrent(items[idx - 1].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, idx]);
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingBlock rows={6} />;
  if (!items.length)
    return (
      <EmptyState title="No interpretations waiting" icon={<Sparkles />}>
        New uploads are analysed automatically; their interpretations appear here for a decision.
      </EmptyState>
    );
  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <ol className="grid max-h-[75vh] content-start gap-1 overflow-y-auto pr-1" aria-label="Interpretations awaiting review">
        {items.map((x, i) => (
          <li key={x.id}>
            <button
              onClick={() => setCurrent(x.id)}
              aria-current={i === idx}
              className={cn("flex w-full items-center gap-3 rounded-md p-1.5 text-left transition-colors", i === idx ? "bg-surface shadow-[0_0_0_1px_var(--line-strong)]" : "hover:bg-sunken")}
            >
              {x.asset ? <AssetThumb asset={x.asset} className="size-12 shrink-0 rounded" showDuration={false} /> : null}
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{x.asset?.title ?? x.asset_id}</span>
                <span className="block text-xs text-muted">
                  {humanize(x.analysis_type)} · {x.confidence != null ? `${Math.round(x.confidence * 100)}%` : "—"} · {relativeTime(x.created_at)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {sel ? (
        <AnalysisReview
          key={sel.id} // fresh editing state for each interpretation
          a={sel}
          onDecided={() => {
            const next = items[idx + 1] ?? items[idx - 1];
            setCurrent(next?.id ?? null);
          }}
        />
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ */
function SuggestionBody({ s, edits, setEdits, editing }: { s: Suggestion; edits: Json; setEdits: (e: Json) => void; editing: boolean }) {
  const p = { ...s.payload, ...edits } as Record<string, unknown>;
  const set = (k: string, v: unknown) => setEdits({ ...edits, [k]: v });
  if (s.suggestion_type === "principle") {
    return editing ? (
      <div className="grid gap-2">
        <Input aria-label="Title" value={String(p.title ?? "")} onChange={(e) => set("title", e.target.value)} />
        <Textarea aria-label="Statement" rows={2} className="font-serif text-md" value={String(p.statement ?? "")} onChange={(e) => set("statement", e.target.value)} />
        <NativeSelect aria-label="Classification" value={String(p.classification ?? "preferred")} onChange={(e) => set("classification", e.target.value)}>
          {CLASSIFICATIONS.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </NativeSelect>
      </div>
    ) : (
      <div className="grid gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <ClassificationTag value={String(p.classification ?? "preferred")} />
          {p.domain_key ? <span className="text-xs text-muted">{humanize(String(p.domain_key))}</span> : null}
        </div>
        <p className="text-md">{String(p.statement ?? "")}</p>
        {p.source_excerpt ? <p className="text-sm text-muted">Source: “{String(p.source_excerpt)}”{p.source_page ? `, page ${p.source_page}` : ""}</p> : null}
      </div>
    );
  }
  if (s.suggestion_type === "aesthetic_concept") {
    return editing ? (
      <div className="grid gap-2">
        <Input aria-label="Name" value={String(p.name ?? "")} onChange={(e) => set("name", e.target.value)} />
        <Textarea aria-label="Definition" rows={2} value={String(p.definition ?? "")} onChange={(e) => set("definition", e.target.value)} />
      </div>
    ) : (
      <p className="text-md">
        <span className="font-medium">{String(p.name)}</span> — {String(p.definition ?? "")}
      </p>
    );
  }
  if (s.suggestion_type === "concept_link") {
    return (
      <p className="text-md">
        This asset {RELATION_LABELS[String(p.relation_type ?? "exemplifies")]} <span className="font-medium">{String(p.concept_name ?? p.concept ?? "a concept")}</span>
      </p>
    );
  }
  if (s.suggestion_type === "tag") return <p className="text-md">Tag the asset “{String(p.tag)}”</p>;
  if (s.suggestion_type === "relationship")
    return (
      <p className="text-md">
        {ENTITY_LABELS[String(p.source_type)]} {RELATION_LABELS[String(p.relation_type)]} {ENTITY_LABELS[String(p.target_type)]}
      </p>
    );
  return <pre className="font-mono text-[12px] text-ink-2">{JSON.stringify(p, null, 2)}</pre>;
}

function SuggestionCard({ s, selected, onToggle }: { s: Suggestion; selected: boolean; onToggle: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const [edits, setEdits] = React.useState<Json>({});
  const decide = useMutation({
    mutationFn: (decision: "accept" | "reject") => ws.req(`/v1/review/suggestions/${s.id}`, { method: "POST", body: { decision, edits: decision === "accept" ? edits : {} } }),
    onSuccess: (_d, decision) => {
      toast.success(
        decision === "accept"
          ? s.suggestion_type === "principle" || s.suggestion_type === "aesthetic_concept"
            ? "Accepted — created as a draft for approval"
            : "Accepted"
          : "Rejected",
      );
      qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });
    },
  });
  const editable = s.suggestion_type === "principle" || s.suggestion_type === "aesthetic_concept";
  return (
    <li className={cn("grid gap-3 rounded-lg border bg-surface p-4 sm:grid-cols-[auto_1fr_auto]", selected ? "border-accent" : "border-line")}>
      <Checkbox checked={selected} onCheckedChange={onToggle} aria-label={`Select ${s.title}`} className="mt-1" />
      <div className="grid min-w-0 gap-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <AiTag label={humanize(s.suggestion_type)} />
          {s.confidence != null ? <span className="text-muted">confidence {Math.round(s.confidence * 100)}%</span> : null}
          <span className="text-muted">{relativeTime(s.created_at)}</span>
        </div>
        <p className="font-medium">{s.title}</p>
        <SuggestionBody s={s} edits={edits} setEdits={setEdits} editing={editing} />
        {s.rationale ? <p className="text-sm text-muted">{s.rationale}</p> : null}
        {s.asset ? (
          <Link href={`${ws.base}/assets/${s.asset.id}`} className="flex w-fit items-center gap-2 text-sm text-muted hover:text-ink">
            <AssetThumb asset={s.asset} className="size-8 rounded" showDuration={false} /> from {s.asset.title}
          </Link>
        ) : null}
      </div>
      <div className="flex flex-wrap items-start gap-1.5 sm:flex-col sm:items-stretch">
        <Button size="sm" variant="primary" disabled={decide.isPending} onClick={() => decide.mutate("accept")}>
          {editing ? "Accept edited" : "Accept"}
        </Button>
        {editable && !editing ? (
          <Button size="sm" onClick={() => setEditing(true)}>
            Edit
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate("reject")}>
          Reject
        </Button>
      </div>
    </li>
  );
}

function SuggestionsTab() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const params = useSearchParams();
  const summary = useReviewSummary();
  const [type, setType] = React.useState(params.get("type") ?? "");
  const assetFilter = params.get("asset");
  const [selected, setSelected] = React.useState<string[]>([]);
  const q = useQuery({
    queryKey: ws.key("review", "suggestions", ws.brand.id, type, assetFilter),
    queryFn: () => ws.req<Page<Suggestion>>("/v1/review/suggestions", { params: { brand_id: ws.brand.id, suggestion_type: type || undefined, asset_id: assetFilter, limit: 100 } }),
  });
  const bulk = useMutation({
    mutationFn: (decision: "accept" | "reject") => ws.req<{ accepted: number; rejected: number; skipped: number }>("/v1/review/suggestions-bulk", { method: "POST", body: { ids: selected, decision } }),
    onSuccess: (r) => {
      toast.success(`${r.accepted + r.rejected} decided${r.skipped ? `, ${r.skipped} skipped` : ""}`);
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });
    },
  });
  const counts = summary.data?.suggestions ?? {};
  const items = q.data?.items ?? [];
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setType("")} className={cn("h-7 rounded-md px-2.5 text-sm", !type ? "bg-ink text-paper" : "bg-sunken hover:bg-line")}>
          All
        </button>
        {Object.entries(counts).map(([k, n]) => (
          <button key={k} onClick={() => setType(k)} className={cn("h-7 rounded-md px-2.5 text-sm", type === k ? "bg-ink text-paper" : "bg-sunken hover:bg-line")}>
            {humanize(k)} <span className="opacity-60">{n}</span>
          </button>
        ))}
        {assetFilter ? (
          <Link href={`${ws.base}/review?tab=suggestions`} className="text-sm text-accent hover:underline">
            Showing one asset — show all
          </Link>
        ) : null}
        {items.length ? (
          <div className="ml-auto flex items-center gap-2">
            <button className="text-sm text-accent hover:underline" onClick={() => setSelected(selected.length === items.length ? [] : items.map((s) => s.id))}>
              {selected.length === items.length ? "Select none" : "Select all"}
            </button>
            <Button size="sm" variant="primary" disabled={!selected.length || bulk.isPending} onClick={() => bulk.mutate("accept")}>
              Accept {selected.length || ""}
            </Button>
            <Button size="sm" disabled={!selected.length || bulk.isPending} onClick={() => bulk.mutate("reject")}>
              Reject {selected.length || ""}
            </Button>
          </div>
        ) : null}
      </div>
      {q.error ? <ErrorState error={q.error} /> : null}
      {!q.data ? (
        <LoadingBlock rows={5} />
      ) : !items.length ? (
        <EmptyState title="No suggestions waiting">AI suggests principles from documents, concept links and tags from assets. Accepted principles and concepts arrive as drafts.</EmptyState>
      ) : (
        <ul className="grid gap-3">
          {items.map((s) => (
            <SuggestionCard key={s.id} s={s} selected={selected.includes(s.id)} onToggle={() => setSelected((x) => (x.includes(s.id) ? x.filter((y) => y !== s.id) : [...x, s.id]))} />
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ */
type ReviewRow = { id: string; subject_type: string; subject_id: string; decision: string; notes: string | null; reviewer_id: string | null; created_at: string; changes: Json };

function HistoryTab() {
  const ws = useWorkspace();
  const name = useMemberNames();
  const q = useQuery({ queryKey: ws.key("review", "history"), queryFn: () => ws.req<Page<ReviewRow>>("/v1/review/history", { params: { limit: 200 } }) });
  if (!q.data) return <LoadingBlock rows={6} />;
  return (
    <Panel>
      <Table>
        <THead>
          <tr>
            <th>When</th>
            <th>What</th>
            <th>Decision</th>
            <th>By</th>
            <th>Note</th>
          </tr>
        </THead>
        <TBody>
          {q.data.items.map((r) => (
            <tr key={r.id}>
              <td className="whitespace-nowrap text-sm text-muted">{formatDateTime(r.created_at)}</td>
              <td className="text-sm">{humanize(r.subject_type)}</td>
              <td>
                <Status status={r.decision === "edited_and_accepted" ? "accepted" : r.decision} label={humanize(r.decision)} />
              </td>
              <td className="text-sm">{name(r.reviewer_id)}</td>
              <td className="text-sm text-muted">{r.notes}</td>
            </tr>
          ))}
        </TBody>
      </Table>
    </Panel>
  );
}

export default function ReviewQueue() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const summary = useReviewSummary();
  const tab = params.get("tab") ?? "interpretations";
  const analyses = Object.values(summary.data?.analyses ?? {}).reduce((a, b) => a + b, 0);
  const suggestions = Object.values(summary.data?.suggestions ?? {}).reduce((a, b) => a + b, 0);
  return (
    <Main wide>
      <PageHeader
        title="AI review queue"
        description="AI output waits here until a person decides. Accepted interpretations enrich search; accepted principles and concepts start as drafts that still need approval."
      />
      {!ws.can("review.decide") ? <p className="mb-4 text-sm text-muted">You can see the queue but not decide; ask a reviewer or creative director.</p> : null}
      <Tabs value={tab} onValueChange={(v) => router.replace(`${pathname}?tab=${v}`, { scroll: false })}>
        <TabsList>
          <TabsTrigger value="interpretations">Interpretations {analyses ? <span className="text-ai">{analyses}</span> : null}</TabsTrigger>
          <TabsTrigger value="suggestions">Suggestions {suggestions ? <span className="text-ai">{suggestions}</span> : null}</TabsTrigger>
          <TabsTrigger value="history">Decision history</TabsTrigger>
        </TabsList>
        <TabsContent value="interpretations">
          <InterpretationsTab />
        </TabsContent>
        <TabsContent value="suggestions">
          <SuggestionsTab />
        </TabsContent>
        <TabsContent value="history">
          <HistoryTab />
        </TabsContent>
      </Tabs>
    </Main>
  );
}
