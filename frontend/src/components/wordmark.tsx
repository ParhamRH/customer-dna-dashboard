import { cn } from "@/lib/utils";

/** Platform mark: a monochrome strip of bars, echoing the per-customer palette strips. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 16" className={cn("h-4 w-6", className)} aria-hidden>
      {[
        [0, 5],
        [6, 2],
        [9.5, 4],
        [15, 1.5],
        [18, 3],
        [22.5, 1.5],
      ].map(([x, w], i) => (
        <rect key={i} x={x} y="0" width={w} height="16" rx="0.5" fill="currentColor" opacity={i % 2 ? 0.55 : 1} />
      ))}
    </svg>
  );
}

export function Wordmark({ className, sub = true }: { className?: string; sub?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <Mark />
      <span className="leading-tight">
        <span className="block text-base font-semibold tracking-[-0.01em]">Brand DNA</span>
        {sub ? <span className="block text-2xs opacity-70">Creative Intelligence Platform</span> : null}
      </span>
    </span>
  );
}
