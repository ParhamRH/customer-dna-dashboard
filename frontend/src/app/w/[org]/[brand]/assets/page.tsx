"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Columns3, Grid2x2, Link2, List, Search, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useStoredPreference } from "@/lib/state";
import { useCollections } from "@/lib/hooks";
import type { AssetFacets, AssetSummary } from "@/lib/types";
import { APPROVAL_LABELS, ASSET_TYPE_LABELS, REFERENCE_ROLE_LABELS } from "@/lib/labels";
import { cn, formatBytes, formatDate, formatNumber, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, NativeSelect } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AssetThumb } from "@/components/asset-thumb";
import { Status, StatusMark } from "@/components/status";
import { useConfirm } from "@/components/confirm";
import { ReferenceDialog, UploadDialog } from "@/components/assets/upload";

type Page = { items: AssetSummary[]; total: number; limit: number; offset: number; facets: AssetFacets };
type View = "grid" | "masonry" | "list";
const PAGE = 60;
const MULTI = ["asset_type", "approval_status", "reference_role", "tag"] as const;

function useFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = (k: string) => params.getAll(k);
  const set = (k: string, values: string[] | string | null) => {
    const next = new URLSearchParams(params.toString());
    next.delete(k);
    (Array.isArray(values) ? values : values ? [values] : []).forEach((v) => next.append(k, v));
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const toggle = (k: string, v: string) => {
    const cur = get(k);
    set(k, cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
  };
  return { params, get, set, toggle, clear: () => router.replace(pathname, { scroll: false }) };
}

function FacetGroup({ title, counts, selected, onToggle, labels }: { title: string; counts: Record<string, number>; selected: string[]; onToggle: (v: string) => void; labels?: Record<string, string> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return (
    <fieldset className="grid gap-1">
      <legend className="mb-1 text-sm font-medium text-ink-2">{title}</legend>
      {entries.map(([k, n]) => (
        <label key={k} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-sunken">
          <Checkbox checked={selected.includes(k)} onCheckedChange={() => onToggle(k)} aria-label={labels?.[k] ?? humanize(k)} />
          <span className="flex-1 truncate">{labels?.[k] ?? humanize(k)}</span>
          <span className="tabular text-xs text-muted">{formatNumber(n)}</span>
        </label>
      ))}
    </fieldset>
  );
}

function AssetCard({ a, selected, selecting, onToggle, href, aspect = "1 / 1" }: { a: AssetSummary; selected: boolean; selecting: boolean; onToggle: () => void; href: string; aspect?: string }) {
  return (
    <div className="group relative" data-testid="asset-card">
      <Link href={href} className="block rounded-md focus-visible:outline-2 focus-visible:outline-ring" onClick={(e) => { if (selecting) { e.preventDefault(); onToggle(); } }}>
        <div style={{ aspectRatio: aspect }}>
          <AssetThumb asset={a} className={cn("size-full rounded-md", selected && "ring-2 ring-accent ring-offset-2 ring-offset-paper")} size={aspect === "1 / 1" ? "thumb" : "preview"} fit="cover" />
        </div>
        <div className="mt-1.5 flex items-start justify-between gap-2">
          <span className="line-clamp-1 text-sm font-medium text-ink group-hover:underline">{a.title}</span>
          <StatusMark status={a.approval_status === "pending" ? "pending_review" : a.approval_status} className="mt-1" />
        </div>
        <p className="truncate text-xs text-muted">
          {ASSET_TYPE_LABELS[a.asset_type] ?? a.asset_type}
          {a.reference_role !== "official" ? ` · ${REFERENCE_ROLE_LABELS[a.reference_role]}` : ""}
          {a.processing_status === "pending" || a.processing_status === "processing" ? " · processing…" : ""}
          {a.processing_status === "failed" ? " · processing failed" : ""}
        </p>
      </Link>
      <div className={cn("absolute left-1.5 top-1.5 rounded bg-surface/90 p-0.5 transition-opacity", selecting || selected ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100")}>
        <Checkbox checked={selected} onCheckedChange={onToggle} aria-label={`Select ${a.title}`} />
      </div>
    </div>
  );
}

function BulkBar({ ids, onDone }: { ids: string[]; onDone: () => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const collections = useCollections();
  const [tags, setTags] = React.useState("");
  const [folder, setFolder] = React.useState("");
  const run = useMutation({
    mutationFn: ({ action, value }: { action: string; value?: unknown }) => ws.req<{ updated: number }>("/v1/assets/bulk", { method: "POST", body: { asset_ids: ids, action, value } }),
    onSuccess: (r) => {
      toast.success(`${r.updated} asset(s) updated`);
      qc.invalidateQueries({ queryKey: ws.key("assets") });
      qc.invalidateQueries({ queryKey: ws.key("collections") });
      onDone();
    },
  });
  return (
    <div role="toolbar" aria-label="Bulk actions" className="sticky bottom-4 z-20 mx-auto mt-6 flex w-fit max-w-full flex-wrap items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-2 shadow-pop">
      <span className="mr-2 text-sm font-medium">{ids.length} selected</span>
      {ws.can("review.decide") ? (
        <>
          <Button size="sm" onClick={() => run.mutate({ action: "set_approval", value: "approved" })}>
            Approve
          </Button>
          <Button size="sm" onClick={() => run.mutate({ action: "set_approval", value: "rejected" })}>
            Reject
          </Button>
        </>
      ) : null}
      {ws.can("assets.write") ? (
        <>
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm">Role</Button>
            </PopoverTrigger>
            <PopoverContent className="grid w-52 gap-1 p-1.5">
              {Object.entries(REFERENCE_ROLE_LABELS).map(([k, v]) => (
                <Button key={k} size="sm" variant="ghost" className="justify-start" onClick={() => run.mutate({ action: "set_role", value: k })}>
                  {v}
                </Button>
              ))}
            </PopoverContent>
          </Popover>
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm">Tag</Button>
            </PopoverTrigger>
            <PopoverContent className="grid gap-2">
              <Input placeholder="tags, comma separated" value={tags} onChange={(e) => setTags(e.target.value)} aria-label="Tags to add" />
              <Button size="sm" variant="primary" disabled={!tags.trim()} onClick={() => run.mutate({ action: "add_tags", value: tags.split(",").map((t) => t.trim()).filter(Boolean) })}>
                Add tags
              </Button>
            </PopoverContent>
          </Popover>
          <Popover>
            <PopoverTrigger asChild>
              <Button size="sm">Move</Button>
            </PopoverTrigger>
            <PopoverContent className="grid gap-2">
              <Input placeholder="/folder/path" value={folder} onChange={(e) => setFolder(e.target.value)} aria-label="Folder" />
              <Button size="sm" variant="primary" onClick={() => run.mutate({ action: "move_folder", value: folder })}>
                Move to folder
              </Button>
            </PopoverContent>
          </Popover>
          <Button size="sm" onClick={() => run.mutate({ action: "reprocess" })}>
            Reprocess
          </Button>
        </>
      ) : null}
      {ws.can("collections.manage") && collections.data?.items.length ? (
        <Popover>
          <PopoverTrigger asChild>
            <Button size="sm">Add to collection</Button>
          </PopoverTrigger>
          <PopoverContent className="grid max-h-72 w-60 gap-1 overflow-y-auto p-1.5">
            {collections.data.items.map((c) => (
              <Button key={c.id} size="sm" variant="ghost" className="justify-start" onClick={() => run.mutate({ action: "add_to_collection", value: c.id })}>
                {c.name}
              </Button>
            ))}
          </PopoverContent>
        </Popover>
      ) : null}
      {ws.can("assets.delete") ? (
        <Button
          size="sm"
          variant="danger-outline"
          onClick={async () => {
            if (await confirm({ title: `Delete ${ids.length} asset(s)?`, description: "They move to the deleted view and are purged permanently after 30 days unless restored.", confirmLabel: "Delete", destructive: true }))
              run.mutate({ action: "delete" });
          }}
        >
          Delete
        </Button>
      ) : null}
      <Button size="icon-sm" variant="ghost" aria-label="Clear selection" onClick={onDone}>
        <X />
      </Button>
    </div>
  );
}

export default function AssetLibrary() {
  const ws = useWorkspace();
  const f = useFilters();
  const [view, setV] = useStoredPreference<View>("bdna-asset-view", "grid", ["grid", "masonry", "list"]);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [selecting, setSelecting] = React.useState(false);
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [refOpen, setRefOpen] = React.useState(false);
  const [q, setQ] = React.useState(f.params.get("q") ?? "");
  React.useEffect(() => {
    const t = setTimeout(() => {
      if ((f.params.get("q") ?? "") !== q) f.set("q", q || null);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);
  const filters = {
    brand_id: ws.brand.id,
    q: f.params.get("q") || undefined,
    asset_type: f.get("asset_type"),
    approval_status: f.get("approval_status"),
    reference_role: f.get("reference_role"),
    tag: f.get("tag"),
    collection_id: f.params.get("collection_id") || undefined,
    concept_id: f.params.get("concept_id") || undefined,
    principle_id: f.params.get("principle_id") || undefined,
    folder: f.params.get("folder") || undefined,
    processing_status: f.params.get("processing_status") || undefined,
    deleted: f.params.get("deleted") === "1" || undefined,
    sort: f.params.get("sort") || (f.params.get("q") ? "relevance" : "newest"),
  };
  const list = useInfiniteQuery({
    queryKey: ws.key("assets", "list", filters),
    queryFn: ({ pageParam }) => ws.req<Page>("/v1/assets", { params: { ...filters, limit: PAGE, offset: pageParam } }),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.limit < last.total ? last.offset + last.limit : undefined),
    refetchInterval: (query) =>
      query.state.data?.pages.some((p) => p.items.some((a) => a.processing_status === "pending" || a.processing_status === "processing")) ? 3000 : false,
  });
  const folders = useQuery({
    queryKey: ws.key("folders", ws.brand.id),
    queryFn: () => ws.req<{ items: { path: string; count: number }[] }>(`/v1/brands/${ws.brand.id}/folders`),
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const total = list.data?.pages[0]?.total ?? 0;
  const facets = list.data?.pages[0]?.facets;
  const toggleSel = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const active = MULTI.some((k) => f.get(k).length) || ["q", "collection_id", "concept_id", "principle_id", "folder", "processing_status", "deleted"].some((k) => f.params.get(k));

  return (
    <Main wide>
      <PageHeader
        title="Asset library"
        description="Every image, film, render, document and reference of the brand — originals stay untouched; previews and analysis are derived."
        actions={
          ws.can("assets.write") ? (
            <>
              <Button onClick={() => setRefOpen(true)}>
                <Link2 /> Add reference
              </Button>
              <Button variant="primary" onClick={() => setUploadOpen(true)}>
                <Upload /> Upload
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="grid gap-8 lg:grid-cols-[13rem_1fr]">
        <aside className="grid content-start gap-5" aria-label="Filters">
          {facets ? (
            <>
              <FacetGroup title="Type" counts={facets.asset_type} labels={ASSET_TYPE_LABELS} selected={f.get("asset_type")} onToggle={(v) => f.toggle("asset_type", v)} />
              <FacetGroup title="Approval" counts={facets.approval_status} labels={APPROVAL_LABELS} selected={f.get("approval_status")} onToggle={(v) => f.toggle("approval_status", v)} />
              <FacetGroup title="Role" counts={facets.reference_role} labels={REFERENCE_ROLE_LABELS} selected={f.get("reference_role")} onToggle={(v) => f.toggle("reference_role", v)} />
              {facets.tags.length ? (
                <fieldset>
                  <legend className="mb-1.5 text-sm font-medium text-ink-2">Tags</legend>
                  <div className="flex flex-wrap gap-1">
                    {facets.tags.slice(0, 24).map((t) => {
                      const on = f.get("tag").includes(t.tag);
                      return (
                        <button key={t.tag} aria-pressed={on} onClick={() => f.toggle("tag", t.tag)} className={cn("h-6 rounded-[4px] px-1.5 text-xs", on ? "bg-ink text-paper" : "bg-sunken text-ink-2 hover:bg-line")}>
                          {t.tag} <span className="opacity-60">{t.count}</span>
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              ) : null}
              {folders.data && folders.data.items.length > 1 ? (
                <fieldset className="grid gap-0.5">
                  <legend className="mb-1 text-sm font-medium text-ink-2">Folders</legend>
                  {folders.data.items.map((fo) => (
                    <button key={fo.path} onClick={() => f.set("folder", f.params.get("folder") === fo.path ? null : fo.path)} className={cn("flex justify-between rounded px-1 py-0.5 text-left text-sm hover:bg-sunken", f.params.get("folder") === fo.path && "bg-sunken font-medium")}>
                      <span className="truncate font-mono text-[12px]">{fo.path}</span>
                      <span className="text-xs text-muted">{fo.count}</span>
                    </button>
                  ))}
                </fieldset>
              ) : null}
              {facets.processing_status.failed ? (
                <button className="text-left text-sm text-danger hover:underline" onClick={() => f.set("processing_status", "failed")}>
                  {facets.processing_status.failed} failed to process
                </button>
              ) : null}
              {ws.can("assets.delete") ? (
                <label className="flex items-center gap-2 text-sm text-muted">
                  <Checkbox checked={f.params.get("deleted") === "1"} onCheckedChange={(v) => f.set("deleted", v ? "1" : null)} /> Show deleted
                </label>
              ) : null}
            </>
          ) : (
            <LoadingBlock rows={6} />
          )}
        </aside>
        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-60 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles, descriptions, tags, file names" className="pl-8" aria-label="Search assets" />
            </div>
            <NativeSelect aria-label="Sort" className="w-40" value={filters.sort} onChange={(e) => f.set("sort", e.target.value)}>
              {filters.q ? <option value="relevance">Most relevant</option> : null}
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="updated">Recently edited</option>
              <option value="title">Title A–Z</option>
              <option value="size">Largest first</option>
            </NativeSelect>
            <Segmented<View>
              label="View"
              value={view}
              onChange={setV}
              options={[
                { value: "grid", label: <Grid2x2 />, title: "Grid" },
                { value: "masonry", label: <Columns3 />, title: "Masonry" },
                { value: "list", label: <List />, title: "List" },
              ]}
            />
            <Button
              size="sm"
              variant={selecting ? "primary" : "secondary"}
              onClick={() => {
                setSelecting(!selecting);
                if (selecting) setSelected([]);
              }}
            >
              <CheckSquare /> Select
            </Button>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span>{list.data ? `${formatNumber(total)} asset${total === 1 ? "" : "s"}` : ""}</span>
            {f.params.get("concept_id") ? <span className="rounded bg-sunken px-1.5">exemplifying a concept</span> : null}
            {f.params.get("principle_id") ? <span className="rounded bg-sunken px-1.5">linked to a principle</span> : null}
            {f.params.get("collection_id") ? <span className="rounded bg-sunken px-1.5">in a collection</span> : null}
            {active ? (
              <button onClick={() => { setQ(""); f.clear(); }} className="text-accent hover:underline">
                Clear filters
              </button>
            ) : null}
            {selecting && items.length ? (
              <button className="ml-auto text-accent hover:underline" onClick={() => setSelected(selected.length === items.length ? [] : items.map((a) => a.id))}>
                {selected.length === items.length ? "Select none" : `Select all ${items.length} shown`}
              </button>
            ) : null}
          </div>
          {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : null}
          {list.isLoading ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
              {Array.from({ length: 10 }).map((_, i) => (
                <div key={i} className="aspect-square animate-pulse rounded-md bg-sunken" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              title={active ? "No assets match these filters" : "The library is empty"}
              action={
                !active && ws.can("assets.write") ? (
                  <Button variant="primary" onClick={() => setUploadOpen(true)}>
                    <Upload /> Upload the first files
                  </Button>
                ) : undefined
              }
            >
              {active ? "Remove a filter or try another search." : "Upload photography, film, renders, documents and references. They are analysed automatically and wait for your review."}
            </EmptyState>
          ) : view === "list" ? (
            <Table>
              <THead>
                <tr>
                  <th className="w-10" />
                  <th className="w-14" />
                  <th>Title</th>
                  <th>Type</th>
                  <th>Role</th>
                  <th>Approval</th>
                  <th className="text-right">Size</th>
                  <th>Added</th>
                </tr>
              </THead>
              <TBody>
                {items.map((a) => (
                  <tr key={a.id} className="hover:bg-surface-2">
                    <td>
                      <Checkbox checked={selected.includes(a.id)} onCheckedChange={() => toggleSel(a.id)} aria-label={`Select ${a.title}`} />
                    </td>
                    <td>
                      <AssetThumb asset={a} className="size-10 rounded" showDuration={false} />
                    </td>
                    <td>
                      <Link href={`${ws.base}/assets/${a.id}`} className="font-medium hover:underline">
                        {a.title}
                      </Link>
                      <div className="truncate text-xs text-muted">{a.original_filename ?? a.source_url}</div>
                    </td>
                    <td className="text-sm">{ASSET_TYPE_LABELS[a.asset_type]}</td>
                    <td className="text-sm">{REFERENCE_ROLE_LABELS[a.reference_role]}</td>
                    <td>
                      <Status status={a.approval_status} />
                    </td>
                    <td className="tabular text-right text-sm">{formatBytes(a.file_size)}</td>
                    <td className="whitespace-nowrap text-sm text-muted">{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </TBody>
            </Table>
          ) : view === "masonry" ? (
            <div className="columns-2 gap-4 sm:columns-3 xl:columns-4">
              {items.map((a) => (
                <MasonryItem key={a.id} a={a} selected={selected.includes(a.id)} selecting={selecting} onToggle={() => toggleSel(a.id)} href={`${ws.base}/assets/${a.id}`} />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3 xl:grid-cols-5">
              {items.map((a) => (
                <AssetCard key={a.id} a={a} selected={selected.includes(a.id)} selecting={selecting} onToggle={() => toggleSel(a.id)} href={`${ws.base}/assets/${a.id}`} />
              ))}
            </div>
          )}
          {list.hasNextPage ? (
            <div className="mt-6 flex justify-center">
              <Button onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                {list.isFetchingNextPage ? "Loading…" : `Show more (${formatNumber(total - items.length)} left)`}
              </Button>
            </div>
          ) : null}
          {selected.length ? <BulkBar ids={selected} onDone={() => setSelected([])} /> : null}
        </div>
      </div>
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} defaults={{ asset_type: f.get("asset_type")[0] === "logo" ? "logo" : undefined }} />
      <ReferenceDialog open={refOpen} onOpenChange={setRefOpen} />
    </Main>
  );
}

function MasonryItem(props: { a: AssetSummary; selected: boolean; selecting: boolean; onToggle: () => void; href: string }) {
  const r = props.a.width && props.a.height ? `${props.a.width} / ${props.a.height}` : "4 / 3";
  return (
    <div className="mb-4 break-inside-avoid">
      <AssetCard {...props} aspect={r} />
    </div>
  );
}
