"use client";
import { useWorkspace } from "@/lib/workspace";
import { KNOWLEDGE_STATUS_LABELS } from "@/lib/labels";
import { NativeSelect } from "@/components/ui/input";

/** Status control for palettes, typography and tokens. "Approved" requires the approve permission. */
export function StatusSelect({ value, onChange, label, className }: { value: string; onChange: (v: string) => void; label: string; className?: string }) {
  const ws = useWorkspace();
  const canApprove = ws.can("knowledge.approve");
  const options = ["draft", "in_review", "approved", "deprecated", "archived"];
  return (
    <NativeSelect aria-label={label} className={className ?? "h-7 w-32 text-sm"} value={value} onChange={(e) => onChange(e.target.value)} disabled={!ws.can("knowledge.write")}>
      {options.map((s) => (
        <option key={s} value={s} disabled={s === "approved" && !canApprove && value !== "approved"}>
          {KNOWLEDGE_STATUS_LABELS[s]}
        </option>
      ))}
    </NativeSelect>
  );
}
