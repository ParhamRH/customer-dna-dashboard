"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { request } from "@/lib/api";
import type { ActivityItem, PlatformOverview } from "@/lib/types";
import { useCustomers } from "@/lib/admin";
import { formatBytes, formatNumber, humanize, pluralize } from "@/lib/utils";
import { JOB_LABELS } from "@/lib/labels";
import { Main } from "@/components/shell";
import { ErrorState, Figure, LoadingBlock, PageHeader, Panel, Section } from "@/components/page";
import { BarList, ColumnChart } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { DnaStrip } from "@/components/dna-strip";
import { NewCustomerDialog } from "@/components/admin/new-customer";
import { ActivityFeed } from "@/components/activity";

function lastDays(n: number, rows: { day: string; count: number }[]) {
  const byDay = new Map(rows.map((r) => [r.day.slice(0, 10), r.count]));
  const out: { label: string; value: number; tooltip: string }[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push({
      label: d.toLocaleDateString("en", { day: "numeric", month: "short" }),
      value: byDay.get(key) ?? 0,
      tooltip: d.toLocaleDateString("en", { weekday: "long", day: "numeric", month: "long" }),
    });
  }
  return out;
}

export default function AdminOverview() {
  const [newOpen, setNewOpen] = React.useState(false);
  const overview = useQuery({ queryKey: ["admin", "overview"], queryFn: () => request<PlatformOverview>("/v1/platform/overview") });
  const activity = useQuery({
    queryKey: ["admin", "activity", 12],
    queryFn: () => request<{ items: ActivityItem[] }>("/v1/platform/activity", { params: { limit: 12 } }),
  });
  const customers = useCustomers();
  const o = overview.data;
  const jobs = o?.jobs.by_status ?? {};
  const attention = (customers.data?.items ?? [])
    .filter((c) => c.status === "active" && c.pending_reviews > 0)
    .sort((a, b) => b.pending_reviews - a.pending_reviews)
    .slice(0, 6);

  return (
    <Main>
      <PageHeader
        title="Platform overview"
        description="Every customer library on this installation, at a glance."
        actions={
          <Button variant="primary" onClick={() => setNewOpen(true)}>
            <Plus /> New customer
          </Button>
        }
      />
      <NewCustomerDialog open={newOpen} onOpenChange={setNewOpen} />
      {overview.error ? <ErrorState error={overview.error} onRetry={() => overview.refetch()} className="mb-6" /> : null}
      {!o ? (
        <LoadingBlock rows={3} />
      ) : (
        <>
          <Panel className="mb-8 grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-6">
            <Figure
              label="Active customers"
              value={formatNumber(o.customers.active ?? 0)}
              hint={o.customers.archived ? `${o.customers.archived} archived` : `${o.customers.total} in total`}
            />
            <Figure label="Assets" value={formatNumber(o.assets.total)} hint={`${o.assets.uploaded_last_7_days} added this week`} />
            <Figure label="Storage" value={formatBytes(o.storage_bytes)} hint="Originals and previews" />
            <Figure label="Awaiting review" value={formatNumber(o.pending_reviews)} hint="AI interpretations and suggestions" />
            <Figure
              label="Processing"
              value={formatNumber((jobs.queued ?? 0) + (jobs.running ?? 0))}
              hint={(jobs.failed ?? 0) + (jobs.dead ?? 0) ? `${(jobs.failed ?? 0) + (jobs.dead ?? 0)} failed` : "No failures"}
            />
            <Figure
              label="Average job"
              value={o.jobs.avg_duration_ms != null ? `${(o.jobs.avg_duration_ms / 1000).toFixed(1)} s` : "—"}
              hint={`${formatNumber(jobs.succeeded ?? 0)} succeeded`}
            />
          </Panel>

          <div className="grid gap-x-10 lg:grid-cols-[3fr_2fr]">
            <Section title="Activity" description="Recorded actions per day, last 14 days (all customers).">
              <ColumnChart title="Recorded actions per day" data={lastDays(14, o.activity_last_14_days)} valueLabel="actions" />
            </Section>
            <Section title="Processing by job type" description="Completed jobs; failures in brackets.">
              {o.jobs.by_type.length ? (
                <BarList
                  items={o.jobs.by_type
                    .sort((a, b) => b.total - a.total)
                    .map((j) => ({
                      key: j.job_type,
                      label: JOB_LABELS[j.job_type] ?? humanize(j.job_type),
                      value: j.succeeded,
                      secondary: j.failed ? `(${j.failed} failed)` : undefined,
                    }))}
                />
              ) : (
                <p className="text-muted">No jobs have run yet.</p>
              )}
            </Section>
          </div>
        </>
      )}

      <div className="grid gap-x-10 lg:grid-cols-[2fr_3fr]">
        <Section
          title="Waiting on review"
          description="Customers with AI interpretations that no one has decided on yet."
          actions={
            <Link href="/admin/customers" className="text-sm text-accent hover:underline">
              All customers
            </Link>
          }
        >
          {customers.isLoading ? (
            <LoadingBlock rows={3} />
          ) : attention.length ? (
            <ul className="divide-y divide-line">
              {attention.map((c) => (
                <li key={c.id} className="py-2.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <Link href={`/w/${c.slug}`} className="font-medium hover:underline">
                      {c.name}
                    </Link>
                    <Link href={`/w/${c.slug}/_/review`} className="text-sm text-ai hover:underline">
                      {pluralize(c.pending_reviews, "item")} to review
                    </Link>
                  </div>
                  <DnaStrip
                    colors={c.palette.map((p) => ({ hex: p.hex, name: p.name, weight: p.role === "primary" ? 3 : 1 }))}
                    height={4}
                    className="mt-1.5"
                    label={c.name}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-base text-muted">Nothing is waiting. Every AI interpretation has been decided.</p>
          )}
        </Section>
        <Section
          title="Recent activity"
          actions={
            <Link href="/admin/activity" className="text-sm text-accent hover:underline">
              Full activity log
            </Link>
          }
        >
          {activity.data ? <ActivityFeed items={activity.data.items} /> : <LoadingBlock rows={5} />}
        </Section>
      </div>
    </Main>
  );
}
