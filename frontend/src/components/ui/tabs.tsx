"use client";
import * as React from "react";
import { Tabs as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;

export function TabsList({ className, ...props }: React.ComponentPropsWithoutRef<typeof T.List>) {
  return <T.List className={cn("flex items-end gap-4 overflow-x-auto border-b border-line [scrollbar-width:none]", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: React.ComponentPropsWithoutRef<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "-mb-px inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent pb-2 pt-1 text-base text-muted transition-colors hover:text-ink data-[state=active]:border-ink data-[state=active]:font-medium data-[state=active]:text-ink focus-visible:outline-2 focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: React.ComponentPropsWithoutRef<typeof T.Content>) {
  return <T.Content className={cn("min-w-0 pt-5 outline-none", className)} {...props} />;
}

/** Segmented control for compact view switches (grid / masonry, compact / standard…). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode; title?: string }[];
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-md border border-line-strong bg-surface p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex h-6 items-center gap-1 rounded-[4px] px-2 text-sm text-muted transition-colors [&_svg]:size-3.5",
            value === o.value ? "bg-sunken font-medium text-ink" : "hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
