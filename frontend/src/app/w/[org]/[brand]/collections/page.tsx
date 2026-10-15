"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useWorkspace } from "@/lib/workspace";
import { useCollections } from "@/lib/hooks";
import type { AssetSummary } from "@/lib/types";
import { pluralize, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { AssetThumb } from "@/components/asset-thumb";
import { CollectionDialog, COLLECTION_KINDS } from "@/components/assets/collection-dialog";

/** Cover large on the left, up to three more stacked on the right. */
function Mosaic({ assets }: { assets: AssetSummary[] }) {
  if (!assets.length) return <div className="flex aspect-[4/3] items-center justify-center rounded-md border border-dashed border-line-strong text-sm text-muted">Empty</div>;
  if (assets.length < 3) return <AssetThumb asset={assets[0]} className="aspect-[4/3] rounded-md" showDuration={false} />;
  const rest = assets.slice(1, 4);
  return (
    <div className="grid aspect-[4/3] grid-cols-[2fr_1fr] grid-rows-[minmax(0,1fr)] gap-1 overflow-hidden rounded-md">
      <AssetThumb asset={assets[0]} className="h-full min-h-0" showDuration={false} />
      <div className="grid h-full min-h-0 gap-1" style={{ gridTemplateRows: `repeat(${rest.length}, minmax(0, 1fr))` }}>
        {rest.map((a) => (
          <AssetThumb key={a.id} asset={a} className="h-full min-h-0" showDuration={false} />
        ))}
      </div>
    </div>
  );
}

export default function CollectionsPage() {
  const ws = useWorkspace();
  const router = useRouter();
  const q = useCollections();
  const [open, setOpen] = React.useState(false);
  return (
    <Main wide>
      <PageHeader
        title="Collections"
        description="Named sets of assets — moodboards, curated hero references, material gathered for a project. An asset can sit in many collections; collections never copy files."
        actions={
          ws.can("collections.manage") ? (
            <Button variant="primary" onClick={() => setOpen(true)}>
              <Plus /> New collection
            </Button>
          ) : undefined
        }
      />
      {q.error ? <ErrorState error={q.error} /> : null}
      {!q.data ? (
        <LoadingBlock rows={4} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No collections yet">Create one here, or select assets in the library and add them to a new collection.</EmptyState>
      ) : (
        <ul className="grid gap-x-5 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {q.data.items.map((c) => (
            <li key={c.id}>
              <Link href={`${ws.base}/collections/${c.id}`} className="group block">
                <Mosaic assets={c.preview ?? (c.cover ? [c.cover] : [])} />
                <div className="mt-2 flex items-baseline justify-between gap-3">
                  <span className="truncate font-medium group-hover:underline">{c.name}</span>
                  <span className="shrink-0 text-sm text-muted">{pluralize(c.asset_count, "asset")}</span>
                </div>
                <div className="text-sm text-muted">
                  {COLLECTION_KINDS[c.kind]?.label} · updated {relativeTime(c.updated_at)}
                </div>
                {c.description ? <p className="mt-1 line-clamp-2 text-sm text-ink-2">{c.description}</p> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <CollectionDialog collection={null} open={open} onOpenChange={setOpen} onSaved={(c) => router.push(`${ws.base}/collections/${c.id}`)} />
    </Main>
  );
}
