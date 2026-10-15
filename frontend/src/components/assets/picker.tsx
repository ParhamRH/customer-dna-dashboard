"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useAssetPicker } from "@/lib/hooks";
import { cn, pluralize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { AssetThumb } from "@/components/asset-thumb";
import { LoadingBlock } from "@/components/page";

/** Choose assets from this brand's library. Assets in `exclude` are shown as already added. */
export function AssetPickerDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Add",
  exclude = [],
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  exclude?: string[];
  pending?: boolean;
  onConfirm: (ids: string[]) => void;
}) {
  const [q, setQ] = React.useState("");
  const [deferred, setDeferred] = React.useState("");
  const [sel, setSel] = useResetState<string[]>([open], () => []);
  React.useEffect(() => {
    const t = setTimeout(() => setDeferred(q), 250);
    return () => clearTimeout(t);
  }, [q]);
  const assets = useAssetPicker(deferred, open);
  const ex = new Set(exclude);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl">
        <DialogHeader title={title} description={description} />
        <DialogBody className="grid gap-3">
          <Input placeholder="Search by title, tag or description" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search assets" autoFocus />
          {!assets.data ? (
            <LoadingBlock rows={3} />
          ) : assets.data.items.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">No assets match.</p>
          ) : (
            <div className="grid max-h-[55vh] grid-cols-3 gap-3 overflow-y-auto p-1 sm:grid-cols-5 lg:grid-cols-6">
              {assets.data.items.map((a) => {
                const added = ex.has(a.id);
                const on = sel.includes(a.id);
                return (
                  <button
                    key={a.id}
                    type="button"
                    disabled={added}
                    aria-pressed={on}
                    onClick={() => setSel(on ? sel.filter((x) => x !== a.id) : [...sel, a.id])}
                    className="text-left disabled:cursor-default"
                    title={added ? `${a.title} — already added` : a.title}
                  >
                    <AssetThumb asset={a} className={cn("aspect-square rounded-md", on && "ring-2 ring-accent ring-offset-2 ring-offset-surface", added && "opacity-40")} showDuration={false} />
                    <span className="mt-1 block truncate text-xs text-muted">{added ? "Already added" : a.title}</span>
                  </button>
                );
              })}
            </div>
          )}
          {assets.data && assets.data.total > assets.data.items.length ? <p className="text-xs text-muted">Showing {assets.data.items.length} of {assets.data.total}. Search to narrow down.</p> : null}
        </DialogBody>
        <DialogFooter>
          <span className="mr-auto text-sm text-muted">{sel.length ? pluralize(sel.length, "asset") + " selected" : ""}</span>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!sel.length || pending} onClick={() => onConfirm(sel)}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
