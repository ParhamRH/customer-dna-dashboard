"use client";
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import type { KnowledgeStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export type Collection = "entries" | "principles" | "guidelines" | "concepts";

const ACTIONS: { action: string; label: string; from: KnowledgeStatus[]; approve?: boolean; tone?: "primary" | "secondary" | "danger-outline" }[] = [
  { action: "submit", label: "Submit for review", from: ["draft", "rejected"] },
  { action: "approve", label: "Approve as official", from: ["draft", "in_review", "rejected", "deprecated"], approve: true, tone: "primary" },
  { action: "reject", label: "Reject", from: ["draft", "in_review"], approve: true, tone: "danger-outline" },
  { action: "deprecate", label: "Deprecate", from: ["approved"], approve: true },
  { action: "archive", label: "Archive", from: ["draft", "in_review", "rejected", "deprecated", "approved"] },
  { action: "restore", label: "Restore as draft", from: ["archived", "rejected", "deprecated"] },
];

const PAST: Record<string, string> = {
  submit: "Submitted for review",
  approve: "Approved — now official brand knowledge",
  reject: "Rejected",
  deprecate: "Deprecated",
  archive: "Archived",
  restore: "Restored as draft",
};

/**
 * Approval workflow buttons. Approval needs the approve permission AND a signed-in person:
 * API tokens and AI can never make knowledge official.
 */
export function GovernanceActions({
  collection,
  id,
  status,
  canApprove,
  writePerm,
  onDone,
}: {
  collection: Collection;
  id: string;
  status: KnowledgeStatus;
  canApprove: boolean;
  writePerm: string;
  onDone?: () => void;
}) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [notes, setNotes] = React.useState("");
  const run = useMutation({
    mutationFn: (action: string) => ws.req(`/v1/knowledge/${collection}/${id}/${action}`, { method: "POST", body: { notes: notes || null } }),
    onSuccess: (_d, action) => {
      toast.success(PAST[action] ?? "Done");
      setNotes("");
      qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });
      onDone?.();
    },
  });
  const available = ACTIONS.filter((a) => a.from.includes(status) && (a.approve ? canApprove : ws.can(writePerm)));
  if (!available.length) return null;
  const decision = available.filter((a) => a.approve);
  const other = available.filter((a) => !a.approve);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {other.map((a) => (
        <Button key={a.action} size="sm" variant="ghost" disabled={run.isPending} onClick={() => run.mutate(a.action)}>
          {a.label}
        </Button>
      ))}
      {decision.map((a) => (
        <Popover key={a.action}>
          <PopoverTrigger asChild>
            <Button size="sm" variant={a.tone ?? "secondary"} disabled={run.isPending}>
              {a.label}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="grid gap-2">
            <p className="text-sm text-ink-2">
              {a.action === "approve"
                ? "Approving makes this version the official brand knowledge used by search, context packages and MCP clients."
                : a.action === "reject"
                  ? "The item stays as history and can be restored later."
                  : "Deprecated knowledge is no longer official but remains in the version history."}
            </p>
            <Input placeholder="Note for the history (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Decision note" />
            <Button size="sm" variant={a.action === "reject" ? "danger" : "primary"} onClick={() => run.mutate(a.action)} disabled={run.isPending}>
              Confirm: {a.label.toLowerCase()}
            </Button>
          </PopoverContent>
        </Popover>
      ))}
    </div>
  );
}
