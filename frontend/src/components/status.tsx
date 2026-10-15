import * as React from "react";
import { Sparkles } from "lucide-react";
import { cn, humanize } from "@/lib/utils";
import { CLASSIFICATION_LABEL, KNOWLEDGE_STATUS_LABELS, ROLE_LABELS } from "@/lib/labels";

/**
 * Status is encoded by SHAPE first, color second, so it survives grayscale and color-blindness:
 *   official / approved   ● solid
 *   in review (human)     ◐ half
 *   AI pending / suggested ◌ dashed amber ring
 *   draft                 ○ hollow
 *   rejected / failed     ⊘ slashed
 *   retired (deprecated, superseded, archived, expired) — hollow, faint
 *   inspiration / external ▨ hatched
 */
type Shape = "solid" | "half" | "dashed" | "hollow" | "slashed" | "retired" | "hatched";

const SHAPE: Record<string, Shape> = {
  approved: "solid",
  official: "solid",
  published: "solid",
  accepted: "solid",
  succeeded: "solid",
  completed: "solid",
  committed: "solid",
  active: "solid",
  validated: "solid",
  in_review: "half",
  running: "half",
  committing: "half",
  validating: "half",
  pending_review: "dashed",
  suggested: "dashed",
  pending: "dashed",
  queued: "dashed",
  uploaded: "dashed",
  draft: "hollow",
  planning: "hollow",
  rejected: "slashed",
  failed: "slashed",
  dead: "slashed",
  invalid: "slashed",
  deprecated: "retired",
  superseded: "retired",
  archived: "retired",
  expired: "retired",
  cancelled: "retired",
  discarded: "retired",
  suspended: "retired",
  pending_deletion: "slashed",
  inspiration: "hatched",
  external: "hatched",
  historical: "retired",
  work_in_progress: "hollow",
};

const TONE: Record<Shape, string> = {
  solid: "text-accent",
  half: "text-ink-2",
  dashed: "text-ai",
  hollow: "text-muted",
  slashed: "text-danger",
  retired: "text-faint",
  hatched: "text-ink-2",
};

export function StatusMark({ status, className, size = 10 }: { status: string | null | undefined; className?: string; size?: number }) {
  const shape = SHAPE[status ?? ""] ?? "hollow";
  const s = size;
  const r = s / 2 - 1;
  const c = s / 2;
  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className={cn("shrink-0", TONE[shape], className)}>
      {shape === "solid" && <circle cx={c} cy={c} r={r} fill="currentColor" />}
      {shape === "half" && (
        <>
          <circle cx={c} cy={c} r={r} fill="none" stroke="currentColor" strokeWidth={1.4} />
          <path d={`M ${c} ${c - r} A ${r} ${r} 0 0 1 ${c} ${c + r} Z`} fill="currentColor" />
        </>
      )}
      {shape === "dashed" && <circle cx={c} cy={c} r={r} fill="none" stroke="currentColor" strokeWidth={1.6} strokeDasharray="2 1.6" />}
      {(shape === "hollow" || shape === "retired") && <circle cx={c} cy={c} r={r} fill="none" stroke="currentColor" strokeWidth={1.4} />}
      {shape === "slashed" && (
        <>
          <circle cx={c} cy={c} r={r} fill="none" stroke="currentColor" strokeWidth={1.4} />
          <line x1={c - r * 0.7} y1={c + r * 0.7} x2={c + r * 0.7} y2={c - r * 0.7} stroke="currentColor" strokeWidth={1.4} />
        </>
      )}
      {shape === "hatched" && (
        <>
          <defs>
            <pattern id={`h${s}`} width="2.5" height="2.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="2.5" stroke="currentColor" strokeWidth="1.1" />
            </pattern>
          </defs>
          <circle cx={c} cy={c} r={r} fill={`url(#h${s})`} stroke="currentColor" strokeWidth={1.2} />
        </>
      )}
    </svg>
  );
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return KNOWLEDGE_STATUS_LABELS[status] ?? humanize(status);
}

/** Inline status: mark + word. Used in tables and headers. */
export function Status({ status, label, className }: { status: string | null | undefined; label?: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-ink-2", className)} data-status={status ?? ""}>
      <StatusMark status={status} />
      {label === "" ? <span className="sr-only">{statusLabel(status)}</span> : (label ?? statusLabel(status))}
    </span>
  );
}

export function Tag({ children, className, tone = "default", title }: { children: React.ReactNode; className?: string; tone?: "default" | "accent" | "ai" | "danger" | "outline"; title?: string }) {
  const tones = {
    default: "bg-sunken text-ink-2",
    accent: "bg-accent-soft text-accent",
    ai: "bg-ai-soft text-ai border border-dashed border-ai-line",
    danger: "bg-danger-soft text-danger",
    outline: "border border-line-strong text-ink-2",
  };
  return (
    <span title={title} className={cn("inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-[4px] px-1.5 text-xs", tones[tone], className)}>
      {children}
    </span>
  );
}

/** Marks content produced by an AI model (never official until a person approves it). */
export function AiTag({ label = "AI interpretation", dev = false, className }: { label?: string; dev?: boolean; className?: string }) {
  return (
    <Tag tone="ai" className={className} title={dev ? "Produced by the development adapter (heuristic, not a real model)" : "Produced by an AI model — not official brand knowledge"}>
      <Sparkles className="size-3" />
      {label}
      {dev ? " · dev adapter" : ""}
    </Tag>
  );
}

const CLASS_TONE: Record<string, string> = {
  mandatory: "border-ink text-ink",
  preferred: "border-accent/60 text-accent",
  optional: "border-line-strong text-muted",
  prohibited: "border-danger/60 text-danger",
  context_dependent: "border-ink-2/50 text-ink-2 border-dashed",
  experimental: "border-ai-line text-ai border-dashed",
};

export function ClassificationTag({ value, className }: { value: string; className?: string }) {
  return (
    <span className={cn("inline-flex h-5 items-center whitespace-nowrap rounded-[4px] border px-1.5 text-xs font-medium", CLASS_TONE[value], className)}>
      {CLASSIFICATION_LABEL[value] ?? humanize(value)}
    </span>
  );
}

export function RoleLabel({ role }: { role: string }) {
  return <span className="text-sm text-ink-2">{ROLE_LABELS[role] ?? humanize(role)}</span>;
}

export function OriginNote({ origin }: { origin: string }) {
  if (origin === "ai_suggestion") return <AiTag label="From AI suggestion" />;
  if (origin === "import") return <Tag tone="outline">Imported</Tag>;
  return null;
}
