"use client";
import Link from "next/link";
import type { ActivityItem } from "@/lib/types";
import { relativeTime } from "@/lib/utils";
import { actionLabel } from "@/lib/labels";

export function ActivityFeed({ items, showCustomer = true }: { items: ActivityItem[]; showCustomer?: boolean }) {
  if (!items.length) return <p className="text-base text-muted">No activity recorded yet.</p>;
  return (
    <ol className="divide-y divide-line">
      {items.map((a) => (
        <li key={a.id} className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 py-2 text-base">
          <span className="min-w-0">
          <span className="font-medium text-ink">{a.actor ?? (a.actor_type === "system" ? "System" : "Unknown")}</span>
          {" "}<span className="text-ink-2">{actionLabel(a.action)}</span>{" "}
          {showCustomer && a.organization_name ? (
            <Link href={`/admin/customers/${a.organization_id}`} className="text-accent hover:underline">
              {a.organization_name}
            </Link>
          ) : null}
          </span>
          <span className="whitespace-nowrap text-sm text-muted" title={a.created_at}>
            {relativeTime(a.created_at)}
          </span>
        </li>
      ))}
    </ol>
  );
}

