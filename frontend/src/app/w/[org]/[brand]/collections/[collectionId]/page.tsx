"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, ImageIcon, MoreHorizontal, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import type { Collection } from "@/lib/types";
import { pluralize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { AssetThumb } from "@/components/asset-thumb";
import { Status } from "@/components/status";
import { APPROVAL_LABELS } from "@/lib/labels";
import { AssetPickerDialog } from "@/components/assets/picker";
import { CollectionDialog, COLLECTION_KINDS } from "@/components/assets/collection-dialog";
import { useConfirm } from "@/components/confirm";

export default function CollectionPage() {
  const { collectionId } = useParams<{ collectionId: string }>();
  const ws = useWorkspace();
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const [edit, setEdit] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const key = ws.key("collection", collectionId);
  const q = useQuery({ queryKey: key, queryFn: () => ws.req<Collection>(`/v1/collections/${collectionId}`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ws.key("collections") });
  };
  const add = useMutation({
    mutationFn: (ids: string[]) => ws.req<{ added: number }>(`/v1/collections/${collectionId}/assets`, { method: "POST", body: { asset_ids: ids } }),
    onSuccess: (r) => {
      refresh();
      setAdding(false);
      toast.success(`Added ${pluralize(r.added, "asset")}`);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/collections/${collectionId}/assets/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const cover = useMutation({
    mutationFn: (id: string) => ws.req(`/v1/collections/${collectionId}`, { method: "PATCH", body: { cover_asset_id: id } }),
    onSuccess: () => {
      refresh();
      toast.success("Cover updated");
    },
  });
  const order = useMutation({
    mutationFn: (ids: string[]) => ws.req(`/v1/collections/${collectionId}/order`, { method: "PUT", body: { asset_ids: ids } }),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Collection>(key);
      if (prev?.assets) qc.setQueryData<Collection>(key, { ...prev, assets: ids.map((i) => prev.assets!.find((a) => a.id === i)!).filter(Boolean) });
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
  const del = useMutation({
    mutationFn: () => ws.req(`/v1/collections/${collectionId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("collections") });
      toast.success("Collection deleted");
      router.push(`${ws.base}/collections`);
    },
  });

  if (q.error) return <Main><ErrorState error={q.error} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={8} /></Main>;
  const c = q.data;
  const assets = c.assets ?? [];
  const can = ws.can("collections.manage");
  const move = (i: number, d: -1 | 1) => {
    const ids = assets.map((a) => a.id);
    const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    order.mutate(ids);
  };
  return (
    <Main wide>
      <Link href={`${ws.base}/collections`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-3.5" /> Collections
      </Link>
      <PageHeader
        title={c.name}
        description={c.description ?? undefined}
        meta={
          <>
            <span>{COLLECTION_KINDS[c.kind]?.label}</span>
            <span>{pluralize(assets.length, "asset")}</span>
          </>
        }
        actions={
          <>
            {ws.can("context.generate") && assets.length ? (
              <Button asChild>
                <Link href={`${ws.base}/context?collection=${c.id}`}>
                  <Sparkles /> Use in context
                </Link>
              </Button>
            ) : null}
            {can ? (
              <>
                <Button variant="primary" onClick={() => setAdding(true)}>
                  <Plus /> Add assets
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label="More actions">
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => setEdit(true)}>
                      <Pencil /> Edit details
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link href={`${ws.base}/assets?collection_id=${c.id}`}>
                        <ImageIcon /> Open in library
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-danger"
                      onSelect={async () => {
                        if (await confirm({ title: `Delete ${c.name}?`, description: "Only the collection is removed. Its assets stay in the library.", confirmLabel: "Delete collection", destructive: true })) del.mutate();
                      }}
                    >
                      <Trash2 /> Delete collection
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : null}
          </>
        }
      />
      {assets.length === 0 ? (
        <EmptyState title="This collection is empty" action={can ? <Button onClick={() => setAdding(true)}><Plus /> Add assets</Button> : undefined}>
          Add assets from the library to start building it.
        </EmptyState>
      ) : (
        <ol className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {assets.map((a, i) => (
            <li key={a.id} className="group relative">
              <Link href={`${ws.base}/assets/${a.id}`} className="block">
                <AssetThumb asset={a} className="aspect-square rounded-md" />
              </Link>
              {c.cover_asset_id === a.id ? <span className="pointer-events-none absolute left-2 top-2 rounded bg-ink/80 px-1.5 py-0.5 text-[11px] font-medium text-paper">Cover</span> : null}
              {can ? (
                <div className="absolute right-1.5 top-1.5 flex items-center rounded-md border border-line bg-surface/95 shadow-pop transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                  <Button variant="ghost" size="icon-sm" aria-label={`Move ${a.title} earlier`} disabled={i === 0} onClick={() => move(i, -1)}>
                    <ChevronLeft />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={`Move ${a.title} later`} disabled={i === assets.length - 1} onClick={() => move(i, 1)}>
                    <ChevronRight />
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${a.title}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem disabled={c.cover_asset_id === a.id} onSelect={() => cover.mutate(a.id)}>
                        Use as cover
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-danger" onSelect={() => remove.mutate(a.id)}>
                        Remove from collection
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ) : null}
              <div className="mt-1.5 min-w-0">
                <Link href={`${ws.base}/assets/${a.id}`} className="block truncate text-sm font-medium hover:underline" title={a.title}>
                  {a.title}
                </Link>
                <Status status={a.approval_status} label={APPROVAL_LABELS[a.approval_status] ?? a.approval_status} className="text-xs" />
                {a.collection_note ? <p className="mt-0.5 line-clamp-2 text-xs text-muted">{a.collection_note}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      )}
      <CollectionDialog collection={c} open={edit} onOpenChange={setEdit} />
      <AssetPickerDialog
        open={adding}
        onOpenChange={setAdding}
        title={`Add to ${c.name}`}
        description="Assets are linked, not copied. Removing them later leaves the library untouched."
        confirmLabel="Add to collection"
        exclude={assets.map((a) => a.id)}
        pending={add.isPending}
        onConfirm={(ids) => add.mutate(ids)}
      />
    </Main>
  );
}
