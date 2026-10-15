import * as React from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-sunken", className)} {...props} />;
}

export function Separator({ className, vertical }: { className?: string; vertical?: boolean }) {
  return <div role="separator" className={cn(vertical ? "w-px self-stretch bg-line" : "h-px w-full bg-line", className)} />;
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line-strong bg-surface-2 px-1 font-sans text-2xs text-muted">{children}</kbd>;
}

/** Thin horizontal meter, e.g. storage used vs quota. */
export function Meter({ value, max, className, tone = "ink", label }: { value: number; max: number; className?: string; tone?: "ink" | "accent" | "ai" | "danger"; label?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const color = { ink: "bg-ink-2", accent: "bg-accent", ai: "bg-ai", danger: "bg-danger" }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-sunken", className)} role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max} aria-label={label}>
      <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-base", className)} {...props} />
    </div>
  );
}
export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("text-left text-sm text-muted [&_th]:border-b [&_th]:border-line [&_th]:px-3 [&_th]:py-2 [&_th]:font-medium [&_th]:whitespace-nowrap", className)} {...props} />;
}
export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_td]:border-b [&_td]:border-line [&_td]:px-3 [&_td]:py-2.5 [&_tr:last-child_td]:border-b-0 [&_tr]:transition-colors", className)} {...props} />;
}
