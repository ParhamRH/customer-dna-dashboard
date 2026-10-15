"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useSearchParams } from "next/navigation";
import { ChevronDown, Download, Plus } from "lucide-react";
import YAML from "yaml";
import { useWorkspace } from "@/lib/workspace";
import { useDomain } from "@/lib/hooks";
import type { DomainView, Guideline, KnowledgeEntry, Principle } from "@/lib/types";
import { cn, downloadText } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ClassificationTag, OriginNote, Status, StatusMark } from "@/components/status";
import { Markdown } from "@/components/markdown";
import { StructuredView } from "./structured";
import { KnowledgeSheet, type SheetTarget } from "./item-sheet";

export function useSheetFromUrl(): [SheetTarget, (t: SheetTarget) => void] {
  const params = useSearchParams();
  const item = params.get("item");
  // ?item=collection:id opens that record (deep links from search, the graph and the review queue)
  const [target, setTarget] = useResetState<SheetTarget>([item], () => {
    const [collection, id] = (item ?? "").split(":");
    return collection && id ? { collection: collection as "entries", id } : null;
  });
  return [target, setTarget];
}

export function EntryArticle({ e, fields, onOpen }: { e: KnowledgeEntry; fields: DomainView["entry_types"][number]["fields"]; onOpen: () => void }) {
  const official = e.status === "approved";
  const [expanded, setExpanded] = React.useState(false);
  const longBody = e.body && e.body.trim() && e.body.trim() !== (e.summary ?? "").trim();
  return (
    <article id={`entry-${e.id}`} className="group border-t border-line py-5 first:border-t-0">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold">
          <button onClick={onOpen} className="text-left hover:underline">
            {e.title}
          </button>
        </h3>
        <div className="flex items-center gap-2">
          <OriginNote origin={e.origin} />
          <Status status={e.status} />
          <Button size="sm" variant="ghost" onClick={onOpen} className="opacity-70 group-hover:opacity-100">
            Open
          </Button>
        </div>
      </header>
      {e.summary ? <p className={cn("mb-3 max-w-[68ch]", official ? "official-text" : "text-md text-ink-2")}>{e.summary}</p> : null}
      <div className="max-w-3xl">
        <StructuredView fields={fields} data={e.structured} official={official} />
      </div>
      {longBody ? (
        <div className="mt-3">
          {expanded ? <Markdown className={official ? "" : "font-sans text-md"}>{e.body}</Markdown> : null}
          <button className="mt-1 inline-flex items-center gap-1 text-sm text-accent hover:underline" onClick={() => setExpanded(!expanded)}>
            <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} /> {expanded ? "Hide document" : "Read document"}
          </button>
        </div>
      ) : null}
    </article>
  );
}

export function PrincipleRow({ p, onOpen, domainLabel }: { p: Principle; onOpen: () => void; domainLabel?: string }) {
  const official = p.status === "approved";
  return (
    <li className="grid gap-1 border-t border-line py-3 first:border-t-0 sm:grid-cols-[8.5rem_1fr_auto] sm:gap-4">
      <div className="flex items-start gap-2 sm:flex-col sm:gap-1">
        <ClassificationTag value={p.classification} />
        <span className="font-mono text-[11px] text-muted">{p.code}</span>
        {domainLabel ? <span className="text-xs text-muted">{domainLabel}</span> : null}
      </div>
      <div className="min-w-0">
        <button onClick={onOpen} className="text-left font-medium hover:underline">
          {p.title}
        </button>
        <p className={cn("mt-0.5 max-w-[68ch]", official ? "official-text text-[1rem]" : "text-base text-ink-2")}>{p.statement}</p>
        {p.scope?.project_types?.length ? <p className="mt-1 text-sm text-muted">Applies to: {p.scope.project_types.join(", ").replace(/_/g, " ")}</p> : null}
      </div>
      <div className="flex items-start gap-2 sm:justify-end">
        <OriginNote origin={p.origin} />
        <Status status={p.status} />
      </div>
    </li>
  );
}

export function GuidelineRow({ g, onOpen }: { g: Guideline; onOpen: () => void }) {
  return (
    <li className="flex items-start justify-between gap-4 border-t border-line py-3 first:border-t-0">
      <div className="min-w-0">
        <button onClick={onOpen} className="text-left font-medium hover:underline">
          {g.title}
        </button>
        {g.summary ? <p className="mt-0.5 text-base text-ink-2">{g.summary}</p> : null}
        {g.applies_to?.project_types?.length ? <p className="mt-1 text-sm text-muted">For {g.applies_to.project_types.join(", ").replace(/_/g, " ")}</p> : null}
      </div>
      <Status status={g.status} />
    </li>
  );
}

function domainExport(d: DomainView, approvedOnly: boolean) {
  const keep = <T extends { status: string }>(xs: T[]) => (approvedOnly ? xs.filter((x) => x.status === "approved") : xs);
  const strip = (o: Record<string, unknown>) => {
    const { organization_id: _o, search_tsv: _s, ...rest } = o;
    void _o;
    void _s;
    return rest;
  };
  return {
    domain: d.domain,
    approved_only: approvedOnly,
    entries: keep(d.entries).map((x) => strip(x as unknown as Record<string, unknown>)),
    principles: keep(d.principles).map((x) => strip(x as unknown as Record<string, unknown>)),
    guidelines: keep(d.guidelines).map((x) => strip(x as unknown as Record<string, unknown>)),
  };
}

/**
 * One knowledge domain: what is documented (coverage), the entries themselves, and the
 * domain's principles and guidelines. `before` / `after` hold domain-specific sections.
 */
export function DomainPage({
  domain,
  intro,
  before,
  after,
  wide,
}: {
  domain: string;
  intro?: React.ReactNode;
  before?: React.ReactNode;
  after?: React.ReactNode;
  wide?: boolean;
}) {
  const ws = useWorkspace();
  const q = useDomain(domain);
  const [target, setTarget] = useSheetFromUrl();
  const canWrite = ws.can("knowledge.write");
  if (q.error) return <Main><ErrorState error={q.error} onRetry={() => q.refetch()} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={8} /></Main>;
  const d = q.data;
  const byType = new Map<string, KnowledgeEntry[]>();
  d.entries.filter((e) => e.status !== "archived").forEach((e) => byType.set(e.entry_type, [...(byType.get(e.entry_type) ?? []), e]));
  const visibleTypes = d.entry_types.filter((t) => byType.has(t.key));
  const exportName = `${ws.brand.slug}-${domain}`;

  return (
    <Main wide={wide}>
      <PageHeader
        title={d.domain.name}
        description={intro ?? d.domain.description}
        actions={
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button>
                  <Download /> Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem onSelect={() => downloadText(`${exportName}.json`, JSON.stringify(domainExport(d, true), null, 2), "application/json")}>Approved knowledge as JSON</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadText(`${exportName}.yaml`, YAML.stringify(domainExport(d, true)), "application/yaml")}>Approved knowledge as YAML</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadText(`${exportName}-all.json`, JSON.stringify(domainExport(d, false), null, 2), "application/json")}>Everything incl. drafts (JSON)</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {canWrite ? (
              <Button variant="primary" onClick={() => setTarget({ collection: "entries", create: true, defaults: { domain_key: domain } })}>
                <Plus /> New entry
              </Button>
            ) : null}
          </>
        }
      />
      {d.entry_types.length > 1 ? (
        <nav aria-label="Coverage" className="mb-8 flex flex-wrap gap-x-1 gap-y-1.5">
          {d.entry_types.map((t) => {
            const entries = byType.get(t.key);
            const best = entries?.find((e) => e.status === "approved") ?? entries?.[0];
            return entries ? (
              <a key={t.key} href={`#type-${t.key}`} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface px-2 text-sm hover:border-line-strong">
                <StatusMark status={best?.status} /> {t.label}
              </a>
            ) : canWrite ? (
              <button
                key={t.key}
                onClick={() => setTarget({ collection: "entries", create: true, defaults: { domain_key: domain, entry_type: t.key, title: t.label } })}
                className="inline-flex h-7 items-center gap-1.5 rounded-md border border-dashed border-line-strong px-2 text-sm text-muted hover:text-ink"
                title={`Document ${t.label.toLowerCase()}`}
              >
                <Plus className="size-3" /> {t.label}
              </button>
            ) : (
              <span key={t.key} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-dashed border-line px-2 text-sm text-faint">
                {t.label}
              </span>
            );
          })}
        </nav>
      ) : null}
      {before}
      {visibleTypes.length === 0 && !before ? (
        <EmptyState
          title="Nothing documented in this domain yet"
          action={
            canWrite ? (
              <Button variant="primary" onClick={() => setTarget({ collection: "entries", create: true, defaults: { domain_key: domain } })}>
                <Plus /> Write the first entry
              </Button>
            ) : undefined
          }
        >
          Entries combine a written document with structured fields that AI tools can read. They start as drafts and become official when approved.
        </EmptyState>
      ) : null}
      {visibleTypes.map((t) => (
        <Section key={t.key} id={`type-${t.key}`} className="mb-6 scroll-mt-6">
          <p className="mb-1 text-sm text-muted">{t.label}</p>
          {byType.get(t.key)!.map((e) => (
            <EntryArticle key={e.id} e={e} fields={t.fields} onOpen={() => setTarget({ collection: "entries", id: e.id })} />
          ))}
        </Section>
      ))}
      {d.principles.length || canWrite ? (
        <Section
          title="Principles in this domain"
          description="Rules with a classification. Approved principles are enforced in every context package."
          actions={
            canWrite ? (
              <Button size="sm" onClick={() => setTarget({ collection: "principles", create: true, defaults: { domain_key: domain } })}>
                <Plus /> Principle
              </Button>
            ) : undefined
          }
        >
          {d.principles.length ? (
            <ul>
              {d.principles.map((p) => (
                <PrincipleRow key={p.id} p={p} onOpen={() => setTarget({ collection: "principles", id: p.id })} />
              ))}
            </ul>
          ) : (
            <p className="text-base text-muted">No principles for this domain yet.</p>
          )}
        </Section>
      ) : null}
      {d.guidelines.length || canWrite ? (
        <Section
          title="Guidelines"
          description="Longer documents explaining how to apply the principles in practice."
          actions={
            canWrite ? (
              <Button size="sm" onClick={() => setTarget({ collection: "guidelines", create: true, defaults: { domain_key: domain } })}>
                <Plus /> Guideline
              </Button>
            ) : undefined
          }
        >
          {d.guidelines.length ? (
            <ul>
              {d.guidelines.map((g) => (
                <GuidelineRow key={g.id} g={g} onOpen={() => setTarget({ collection: "guidelines", id: g.id })} />
              ))}
            </ul>
          ) : (
            <p className="text-base text-muted">No guidelines for this domain yet.</p>
          )}
        </Section>
      ) : null}
      {after}
      <KnowledgeSheet target={target} onClose={() => setTarget(null)} />
    </Main>
  );
}
