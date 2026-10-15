"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ImageUp, Search as SearchIcon } from "lucide-react";
import { useWorkspace } from "@/lib/workspace";
import { upload } from "@/lib/api";
import type { SearchItem, SearchResult } from "@/lib/types";
import { ENTITY_LABELS } from "@/lib/labels";
import { cn, formatDuration, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Segmented } from "@/components/ui/tabs";
import { AssetThumb } from "@/components/asset-thumb";
import { ClassificationTag, StatusMark, Tag } from "@/components/status";
import { entityHref } from "@/components/knowledge/item-tabs";

const EXAMPLES = [
  "Find approved references with organic geometry",
  "Find images demonstrating material expression",
  "Find videos with slow cinematic camera movements",
  "Find references with muted palettes and dramatic lighting",
  "Find guidelines relevant to website design",
];

const TYPES = ["asset", "principle", "guideline", "aesthetic_concept", "knowledge_entry", "project", "collection"] as const;
type Scope = "all" | "official" | "pending";

const STATUS_COPY: Record<string, { label: string; mark: string }> = {
  official: { label: "Official", mark: "official" },
  pending: { label: "Pending review", mark: "pending_review" },
  inspiration: { label: "Inspiration", mark: "inspiration" },
  external: { label: "External", mark: "external" },
  historical: { label: "Historical", mark: "historical" },
};

function Signals({ s }: { s: NonNullable<SearchItem["signals"]> }) {
  return (
    <dl className="mt-2 grid grid-cols-[6rem_1fr_3rem] items-center gap-x-2 gap-y-0.5 text-xs text-muted">
      {Object.entries(s).map(([k, v]) => (
        <React.Fragment key={k}>
          <dt>{humanize(k)}</dt>
          <dd className="h-1.5 overflow-hidden rounded-full bg-sunken">
            <span className="block h-full bg-ink-2" style={{ width: `${Math.round(v.fused * 100)}%` }} />
          </dd>
          <dd className="tabular">#{v.rank}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function ResultRow({ item, rank, explain }: { item: SearchItem; rank: number; explain: boolean }) {
  const ws = useWorkspace();
  const st = STATUS_COPY[item.knowledge_status] ?? { label: humanize(item.knowledge_status), mark: item.knowledge_status };
  const href = entityHref(ws.base, item.entity_type, item.id);
  return (
    <li className="grid grid-cols-[2rem_5rem_1fr] gap-4 border-t border-line py-4 first:border-t-0">
      <span className="tabular pt-1 text-sm text-faint">{rank}</span>
      <Link href={href} className="block">
        {item.asset ? (
          <AssetThumb asset={item.asset} className="aspect-square rounded-md" />
        ) : (
          <div className="flex aspect-square items-center justify-center rounded-md bg-sunken text-xs text-muted">{ENTITY_LABELS[item.entity_type]?.split(" ")[0]}</div>
        )}
      </Link>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link href={href} className="font-medium hover:underline">
            {item.title}
          </Link>
          <span className="text-sm text-muted">{item.asset ? humanize(item.asset.asset_type) : ENTITY_LABELS[item.entity_type]}</span>
          {item.classification ? <ClassificationTag value={item.classification} /> : null}
          <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
            <StatusMark status={st.mark} /> {st.label}
          </span>
        </div>
        {item.snippet ? <p className="mt-1 line-clamp-2 text-base text-ink-2">{item.snippet}</p> : null}
        {item.matched_segments?.length ? (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.matched_segments.map((m, i) => (
              <Tag key={i} tone="outline">
                {m.start_ms != null ? `scene at ${formatDuration(m.start_ms / 1000)}` : m.page_number ? `page ${m.page_number}` : m.title ?? "segment"}
              </Tag>
            ))}
          </div>
        ) : null}
        {item.asset?.tags.length ? <p className="mt-1 truncate text-xs text-muted">{item.asset.tags.slice(0, 8).join(" · ")}</p> : null}
        {explain && item.signals ? <Signals s={item.signals} /> : null}
      </div>
    </li>
  );
}

export default function SearchPage() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = React.useState(params.get("q") ?? "");
  const [scope, setScope] = React.useState<Scope>("all");
  const [types, setTypes] = React.useState<string[]>([...TYPES]);
  const [historical, setHistorical] = React.useState(true);
  const [explain, setExplain] = React.useState(false);
  const [visualName, setVisualName] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const text = useMutation({
    mutationFn: (query: string) =>
      ws.req<SearchResult>("/v1/search", {
        method: "POST",
        body: { query, brand_id: ws.brand.id, entity_types: types, scope, include_historical: historical, explain: true, limit: 30 },
      }),
  });
  const visual = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("image", f);
      form.append("brand_id", ws.brand.id);
      form.append("limit", "30");
      return upload<SearchResult>("/v1/search/visual", form, { org: ws.orgId });
    },
  });
  const run = (query: string) => {
    setVisualName(null);
    visual.reset();
    router.replace(`${pathname}?q=${encodeURIComponent(query)}`, { scroll: false });
    text.mutate(query);
  };
  const initial = React.useRef(false);
  React.useEffect(() => {
    if (!initial.current && params.get("q")) {
      initial.current = true;
      text.mutate(params.get("q")!);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  React.useEffect(() => {
    if (text.data && !visualName) text.mutate(text.data.query);
    // re-run with new filters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, types, historical]);

  const result = visualName ? visual.data : text.data;
  const pending = text.isPending || visual.isPending;
  const error = visualName ? visual.error : text.error;
  const it = result?.interpreted;

  return (
    <Main>
      <PageHeader title="Search" description="Ask in plain language. Search combines keywords, meaning, the knowledge graph and measured media properties — and only ever this workspace." />
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) run(q.trim());
        }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. references with muted palettes and dramatic lighting" className="h-11 pl-9 text-md" aria-label="Search query" autoFocus />
        </div>
        <Button type="submit" variant="primary" size="lg" disabled={!q.trim() || pending}>
          Search
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              setVisualName(f.name);
              text.reset();
              visual.mutate(f);
            }
            e.target.value = "";
          }}
        />
        <Button size="lg" onClick={() => fileRef.current?.click()} title="Find assets that look like an image">
          <ImageUp /> By image
        </Button>
      </form>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Segmented<Scope>
          label="Scope"
          value={scope}
          onChange={setScope}
          options={[
            { value: "all", label: "Everything" },
            { value: "official", label: "Official only" },
            { value: "pending", label: "Pending only" },
          ]}
        />
        <div className="flex flex-wrap gap-1" role="group" aria-label="Result types">
          {TYPES.map((t) => {
            const on = types.includes(t);
            return (
              <button
                key={t}
                aria-pressed={on}
                onClick={() => setTypes(on ? types.filter((x) => x !== t) : [...types, t])}
                className={cn("h-6 rounded-full border px-2.5 text-sm", on ? "border-ink bg-ink text-paper" : "border-line-strong text-muted hover:text-ink")}
              >
                {ENTITY_LABELS[t]}
              </button>
            );
          })}
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <Switch checked={historical} onCheckedChange={setHistorical} /> Include historical
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <Switch checked={explain} onCheckedChange={setExplain} /> Explain ranking
        </label>
      </div>

      {!result && !pending && !error ? (
        <div className="mt-10">
          <p className="mb-2 text-sm text-muted">Try</p>
          <ul className="grid gap-1.5">
            {EXAMPLES.map((e) => (
              <li key={e}>
                <button
                  className="text-left text-md text-accent hover:underline"
                  onClick={() => {
                    setQ(e);
                    run(e);
                  }}
                >
                  {e}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {error ? <ErrorState className="mt-6" error={error} /> : null}
      {pending ? <LoadingBlock className="mt-8" rows={5} /> : null}
      {result && !pending ? (
        <div className="mt-8">
          <div className="mb-4 rounded-md border border-line bg-surface-2 px-4 py-3 text-sm">
            {visualName ? (
              <p>
                Assets that look like <span className="font-medium">{visualName}</span>, by visual embedding similarity.
              </p>
            ) : (
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-muted">Understood as</span>
                <span className="font-medium">“{it?.text || result.query}”</span>
                {it?.approved_only ? <Tag tone="accent">approved only</Tag> : null}
                {it?.asset_types.map((t) => (
                  <Tag key={t}>{humanize(t)}</Tag>
                ))}
                {it?.attributes.map((t) => (
                  <Tag key={t}>{t}</Tag>
                ))}
                {it?.project_types.map((t) => (
                  <Tag key={t}>for {humanize(t)}</Tag>
                ))}
                {it?.matched_entities.map((m) => (
                  <Tag key={m.id} tone="outline">
                    {ENTITY_LABELS[m.type]}: {m.label}
                  </Tag>
                ))}
              </p>
            )}
            <p className="mt-1 text-xs text-muted">
              {result.total_candidates} candidates · signals: {result.signals_used.map(humanize).join(", ") || "none"}
              {result.embedding_model ? ` · embeddings: ${result.embedding_model}` : ""}
            </p>
          </div>
          {result.items.length === 0 ? (
            <EmptyState title="Nothing found">Try fewer words, widen the scope, or include more result types.</EmptyState>
          ) : (
            <ol>
              {result.items.map((item, i) => (
                <ResultRow key={`${item.entity_type}:${item.id}`} item={item} rank={i + 1} explain={explain} />
              ))}
            </ol>
          )}
        </div>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {result ? `${result.items.length} results` : ""}
      </span>
    </Main>
  );
}
