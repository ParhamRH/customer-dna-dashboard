"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Search, Sparkles } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useWorkspace } from "@/lib/workspace";
import { useConcepts, useDomain } from "@/lib/hooks";
import type { AssetSummary, Concept, Relationship } from "@/lib/types";
import { RELEVANCE } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { AssetThumb } from "@/components/asset-thumb";
import { OriginNote, Status } from "@/components/status";
import { KnowledgeSheet, type SheetTarget } from "@/components/knowledge/item-sheet";
import { EntryArticle } from "@/components/knowledge/domain-page";

function useConceptExamples(conceptId: string, limit = 4) {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("assets", "concept", conceptId, limit),
    queryFn: () => ws.req<{ items: AssetSummary[]; total: number }>("/v1/assets", { params: { brand_id: ws.brand.id, concept_id: conceptId, limit } }),
    enabled: ws.can("assets.read"),
  });
}

function ConceptCard({ c, onOpen }: { c: Concept; onOpen: () => void }) {
  const ex = useConceptExamples(c.id);
  const official = c.status === "approved";
  return (
    <button onClick={onOpen} className={cn("group grid w-full gap-2 rounded-lg border bg-surface p-3 text-left transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-ring", c.brand_relevance === "avoid" ? "border-danger/25" : "border-line")}>
      <div className="flex items-start justify-between gap-2">
        <span className={cn("font-semibold", c.brand_relevance === "avoid" && "text-danger")}>{c.name}</span>
        <Status status={c.status} label="" />
      </div>
      <p className={cn("line-clamp-3", official ? "font-serif text-[15px] leading-snug text-ink-2" : "text-sm text-muted")}>{c.definition}</p>
      {ex.data?.items.length ? (
        <div className="grid grid-cols-4 gap-1">
          {ex.data.items.map((a) => (
            <AssetThumb key={a.id} asset={a} className="aspect-square rounded-[3px]" showDuration={false} />
          ))}
        </div>
      ) : (
        <span className="text-xs text-faint">No example assets linked yet</span>
      )}
      {c.synonyms?.length ? <span className="text-xs text-muted">also: {c.synonyms.join(", ")}</span> : null}
    </button>
  );
}

function RelChips({ label, rels, onPick }: { label: string; rels?: Relationship[]; onPick: (id: string) => void }) {
  if (!rels?.length) return null;
  return (
    <div>
      <p className="mb-1 text-sm text-muted">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {rels.map((r) => (
          <button key={r.id} onClick={() => onPick(r.other_id)} className="h-6 rounded-full border border-line-strong px-2.5 text-sm hover:bg-sunken">
            {r.other_label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ConceptDetail({ id, onClose, onPick, onEdit }: { id: string; onClose: () => void; onPick: (id: string) => void; onEdit: () => void }) {
  const ws = useWorkspace();
  const q = useQuery({ queryKey: ws.key("item", "concepts", id), queryFn: () => ws.req<Concept>(`/v1/knowledge/concepts/${id}`) });
  const examples = useConceptExamples(id, 24);
  const c = q.data;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-6 pb-4 pt-5 pr-12">
        <DialogPrimitive.Title className="text-2xl font-semibold">{c?.name ?? "…"}</DialogPrimitive.Title>
        {c ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-3 text-sm text-muted">
            <span className={c.brand_relevance === "avoid" ? "text-danger" : ""}>{RELEVANCE.find((r) => r.key === c.brand_relevance)?.label} · {RELEVANCE.find((r) => r.key === c.brand_relevance)?.hint}</span>
            <Status status={c.status} />
            <span>Version {c.version}</span>
            <OriginNote origin={c.origin} />
          </div>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {!c ? (
          <LoadingBlock rows={6} />
        ) : (
          <div className="grid gap-6">
            <p className={c.status === "approved" ? "official-text text-xl" : "text-lg text-ink-2"}>{c.definition}</p>
            {c.attributes?.length ? (
              <div>
                <p className="mb-1 text-sm text-muted">Attributes</p>
                <ul className="flex flex-wrap gap-1.5">
                  {c.attributes.map((a, i) => (
                    <li key={i} className="rounded-[4px] bg-sunken px-2 py-0.5 text-sm">
                      {String(a)}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {c.synonyms?.length ? <p className="text-sm"><span className="text-muted">Synonyms: </span>{c.synonyms.join(", ")}</p> : null}
            <div className="grid gap-3 sm:grid-cols-2">
              <RelChips label="Related" rels={c.related_concepts} onPick={onPick} />
              <RelChips label="Opposed by" rels={c.opposing_concepts} onPick={onPick} />
              <RelChips label="Broader" rels={c.broader_concepts} onPick={onPick} />
              <RelChips label="Narrower" rels={c.narrower_concepts} onPick={onPick} />
            </div>
            <div>
              <div className="mb-2 flex items-baseline justify-between">
                <p className="font-medium">Example assets</p>
                {c.suggested_example_count ? (
                  <Link href={`${ws.base}/review?tab=suggestions&type=concept_link`} className="inline-flex items-center gap-1 text-sm text-ai hover:underline">
                    <Sparkles className="size-3.5" /> {c.suggested_example_count} suggested by AI
                  </Link>
                ) : null}
              </div>
              {examples.data?.items.length ? (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {examples.data.items.map((a) => (
                    <Link key={a.id} href={`${ws.base}/assets/${a.id}`} className="group">
                      <AssetThumb asset={a} className="aspect-square rounded-md" />
                      <span className="mt-1 block truncate text-xs text-muted group-hover:text-ink">{a.title}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">No approved examples. Link assets from the asset page, or accept AI suggestions in the review queue.</p>
              )}
            </div>
          </div>
        )}
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-surface-2 px-6 py-3">
        {ws.can("search.use") && c ? (
          <Button size="sm" variant="ghost" asChild>
            <Link href={`${ws.base}/search?q=${encodeURIComponent(c.name)}`}>
              <Search /> Find more like this
            </Link>
          </Button>
        ) : null}
        <Button size="sm" onClick={onEdit}>
          <Pencil /> {ws.can("concepts.manage") ? "Edit, approve, history" : "Details and history"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  );
}

export default function AestheticExplorer() {
  const ws = useWorkspace();
  const router = useRouter();
  const params = useSearchParams();
  const concepts = useConcepts();
  const domain = useDomain("aesthetic_language");
  const [filter, setFilter] = React.useState("");
  const [sheet, setSheet] = React.useState<SheetTarget>(null);
  const selected = params.get("concept");
  const select = (id: string | null) => router.replace(id ? `${ws.base}/aesthetics?concept=${id}` : `${ws.base}/aesthetics`, { scroll: false });
  if (concepts.error) return <Main><ErrorState error={concepts.error} /></Main>;
  const f = filter.trim().toLowerCase();
  const items = (concepts.data?.items ?? []).filter(
    (c) => c.status !== "archived" && (!f || c.name.toLowerCase().includes(f) || c.definition.toLowerCase().includes(f) || c.synonyms.some((s) => s.toLowerCase().includes(f))),
  );
  return (
    <Main wide>
      <PageHeader
        title="Aesthetic explorer"
        description="The brand's controlled vocabulary of aesthetic concepts, from what defines it to what it must avoid. Concepts connect to example assets, principles and projects."
        actions={
          ws.can("concepts.manage") ? (
            <Button variant="primary" onClick={() => setSheet({ collection: "concepts", create: true })}>
              <Plus /> New concept
            </Button>
          ) : undefined
        }
      />
      <div className="mb-5 max-w-xs">
        <Input placeholder="Filter concepts or synonyms" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter concepts" />
      </div>
      {!concepts.data ? (
        <LoadingBlock rows={6} />
      ) : items.length === 0 ? (
        <EmptyState title={f ? "No concept matches" : "No aesthetic concepts yet"}>Define the concepts that describe the brand’s look — for example organic geometry or sculptural minimalism.</EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-5">
          {RELEVANCE.map((band) => {
            const inBand = items.filter((c) => c.brand_relevance === band.key);
            return (
              <section key={band.key} aria-label={band.label} className="min-w-0">
                <header className={cn("mb-3 border-t-2 pt-2", band.key === "avoid" ? "border-danger" : band.key === "core" ? "border-ink" : "border-line-strong")}>
                  <h2 className="font-semibold">{band.label}</h2>
                  <p className="text-sm text-muted">{band.hint}</p>
                </header>
                <div className="grid gap-3">
                  {inBand.map((c) => (
                    <ConceptCard key={c.id} c={c} onOpen={() => select(c.id)} />
                  ))}
                  {!inBand.length ? <p className="text-sm text-faint">—</p> : null}
                </div>
              </section>
            );
          })}
        </div>
      )}
      {domain.data?.entries.length ? (
        <Section title="Ontology notes" className="mt-12">
          {domain.data.entries.map((e) => (
            <EntryArticle key={e.id} e={e} fields={domain.data!.entry_types.find((t) => t.key === e.entry_type)?.fields ?? []} onOpen={() => setSheet({ collection: "entries", id: e.id })} />
          ))}
        </Section>
      ) : null}
      <Dialog open={!!selected} onOpenChange={(o) => !o && select(null)}>
        {selected ? (
          <SheetContent width="w-[min(680px,100vw)]" aria-describedby={undefined}>
            <ConceptDetail
              key={selected}
              id={selected}
              onClose={() => select(null)}
              onPick={(id) => select(id)}
              onEdit={() => {
                setSheet({ collection: "concepts", id: selected });
                select(null);
              }}
            />
          </SheetContent>
        ) : null}
      </Dialog>
      <KnowledgeSheet target={sheet} onClose={() => setSheet(null)} />
    </Main>
  );
}
