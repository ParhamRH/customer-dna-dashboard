"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { errorMessage } from "@/lib/api";
import type { Collection } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";

export const COLLECTION_KINDS: Record<Collection["kind"], { label: string; hint: string }> = {
  collection: { label: "Collection", hint: "A working set of assets." },
  moodboard: { label: "Moodboard", hint: "A visual direction, often with inspiration." },
  curated_set: { label: "Curated set", hint: "A deliberate, reviewed selection — e.g. hero references." },
  project_board: { label: "Project board", hint: "Material gathered for one project." },
};

export function CollectionDialog({
  collection,
  open,
  onOpenChange,
  onSaved,
}: {
  collection: Collection | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved?: (c: Collection) => void;
}) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [f, setF] = useResetState([open, collection?.id], () =>
    collection ? { name: collection.name, description: collection.description ?? "", kind: collection.kind } : { name: "", description: "", kind: "collection" as Collection["kind"] },
  );
  const save = useMutation({
    mutationFn: () => {
      const body = { name: f.name, description: f.description || null, kind: f.kind };
      return collection
        ? ws.req<Collection>(`/v1/collections/${collection.id}`, { method: "PATCH", body })
        : ws.req<Collection>(`/v1/brands/${ws.brand.id}/collections`, { method: "POST", body });
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ws.key("collections") });
      qc.invalidateQueries({ queryKey: ws.key("collection", c.id) });
      toast.success(collection ? "Collection saved" : "Collection created");
      onOpenChange(false);
      onSaved?.(c);
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader title={collection ? "Edit collection" : "New collection"} />
        <DialogBody className="grid gap-4">
          <Field label="Name" htmlFor="col-name">
            <Input id="col-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus />
          </Field>
          <Field label="Kind" htmlFor="col-kind" hint={COLLECTION_KINDS[f.kind].hint}>
            <NativeSelect id="col-kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as Collection["kind"] })}>
              {Object.entries(COLLECTION_KINDS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Description" htmlFor="col-desc">
            <Textarea id="col-desc" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name.trim() || save.isPending} onClick={() => save.mutate()}>
            {collection ? "Save" : "Create collection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
