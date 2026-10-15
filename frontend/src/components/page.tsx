import * as React from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";

export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 max-w-3xl">
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {description ? <p className="mt-1 text-md text-muted">{description}</p> : null}
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">{meta}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
  id,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("mb-10", className)}>
      {title || actions ? (
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-sm text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** A white sheet on the paper background. Used sparingly for grouped tables and forms. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-line bg-surface", className)} {...props} />;
}

export function EmptyState({
  title,
  children,
  action,
  className,
  icon,
}: {
  title: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-2 rounded-lg border border-dashed border-line-strong px-6 py-8", className)}>
      {icon ? <div className="text-faint [&_svg]:size-6">{icon}</div> : null}
      <p className="text-md font-medium text-ink">{title}</p>
      {children ? <div className="max-w-xl text-base text-muted">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-base", className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-danger">Could not load this view</p>
        <p className="mt-0.5 text-ink-2">{errorMessage(error)}</p>
      </div>
      {onRetry ? (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RotateCw /> Try again
        </Button>
      ) : null}
    </div>
  );
}

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("grid gap-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9" style={{ opacity: 1 - i * 0.15 }} />
      ))}
    </div>
  );
}

/** Small labelled figure for overview rows. */
export function Figure({ label, value, hint, className }: { label: React.ReactNode; value: React.ReactNode; hint?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-ink">{value}</div>
      {hint ? <div className="mt-0.5 text-sm text-muted">{hint}</div> : null}
    </div>
  );
}

/** Definition list for metadata panels. */
export function MetaList({ items, className }: { items: [React.ReactNode, React.ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1.5 text-base", className)}>
      {items
        .filter(([, v]) => v !== null && v !== undefined && v !== "")
        .map(([k, v], i) => (
          <React.Fragment key={i}>
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words text-ink">{v}</dd>
          </React.Fragment>
        ))}
    </dl>
  );
}
