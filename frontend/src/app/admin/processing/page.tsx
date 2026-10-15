"use client";
import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCw } from "lucide-react";
import { toast } from "sonner";
import { request } from "@/lib/api";
import type { Job, Page } from "@/lib/types";
import { useCustomers } from "@/lib/admin";
import { JOB_LABELS } from "@/lib/labels";
import { formatDateTime, formatNumber, humanize, pluralize, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/tabs";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Status } from "@/components/status";
import { AiProviders, type AiSettings } from "@/components/admin/ai";

type Settings = { ai: AiSettings; workers: { concurrency: number; queue: Record<string, number>; oldest_runnable_job_at: string | null } };
type JobFilter = "all" | "queued" | "running" | "failed" | "dead" | "succeeded";

export default function ProcessingPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = React.useState<JobFilter>("all");
  const settings = useQuery({ queryKey: ["admin", "settings"], queryFn: () => request<Settings>("/v1/platform/settings") });
  const customers = useCustomers();
  const jobs = useQuery({
    queryKey: ["admin", "jobs", filter],
    queryFn: () => request<Page<Job>>("/v1/platform/jobs", { params: { status: filter === "all" ? undefined : filter, limit: 100 } }),
    refetchInterval: 5000,
  });
  const retry = useMutation({
    mutationFn: (j: Job) => request<Job>(`/v1/jobs/${j.id}/retry`, { method: "POST", org: j.organization_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "jobs"] });
      toast.success("Job queued again");
    },
  });
  const pending = (customers.data?.items ?? []).filter((c) => c.pending_reviews > 0);
  const queue = settings.data?.workers.queue ?? {};

  return (
    <Main wide>
      <PageHeader
        title="AI processing"
        description="Background ingestion, analysis and indexing across customers. AI output always waits for a person in the customer's review queue."
      />
      <div className="grid gap-x-10 xl:grid-cols-[3fr_2fr]">
        <Section title="Models in use" description="Configured per installation; customers can override providers in their integration settings.">
          {settings.data ? <AiProviders ai={settings.data.ai} /> : <LoadingBlock rows={4} />}
          {settings.data && Object.values(settings.data.ai).some((v) => typeof v === "object" && "development_adapter" in v && v.development_adapter) ? (
            <p className="mt-3 max-w-2xl text-sm text-muted">
              Development adapters derive descriptions from measured image, video and document properties. They are labelled on every
              analysis and are never presented as model output. Add an Anthropic or OpenAI key to use a real model.
            </p>
          ) : null}
        </Section>
        <Section title="Waiting for review" description="AI interpretations and suggestions per customer.">
          {pending.length === 0 ? (
            <p className="text-muted">Nothing is waiting.</p>
          ) : (
            <ul className="divide-y divide-line">
              {pending.map((c) => (
                <li key={c.id} className="flex items-center justify-between py-2">
                  <span>{c.name}</span>
                  <Link href={`/w/${c.slug}/_/review`} className="text-sm text-ai hover:underline">
                    {pluralize(c.pending_reviews, "item")}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
      <Section
        title="Job queue"
        description={
          settings.data
            ? `${settings.data.workers.concurrency} worker threads per process. ${formatNumber(queue.queued ?? 0)} queued, ${formatNumber(queue.running ?? 0)} running${
                settings.data.workers.oldest_runnable_job_at ? `; oldest waiting since ${relativeTime(settings.data.workers.oldest_runnable_job_at)}` : ""
              }.`
            : undefined
        }
        actions={
          <Segmented<JobFilter>
            label="Job status"
            value={filter}
            onChange={setFilter}
            options={(["all", "queued", "running", "failed", "dead", "succeeded"] as JobFilter[]).map((v) => ({ value: v, label: humanize(v) }))}
          />
        }
      >
        {jobs.error ? <ErrorState error={jobs.error} /> : null}
        {!jobs.data ? (
          <LoadingBlock rows={6} />
        ) : jobs.data.items.length === 0 ? (
          <EmptyState title="No jobs with this status" />
        ) : (
          <Panel>
            <Table>
              <THead>
                <tr>
                  <th>Job</th>
                  <th>Customer</th>
                  <th>Status</th>
                  <th className="text-right">Attempts</th>
                  <th>Created</th>
                  <th>Duration</th>
                  <th>Error</th>
                  <th className="w-0" />
                </tr>
              </THead>
              <TBody>
                {jobs.data.items.map((j) => (
                  <tr key={j.id} className="align-top">
                    <td>
                      {JOB_LABELS[j.job_type] ?? j.job_type}
                      <div className="font-mono text-[11px] text-faint">{j.id.slice(0, 8)}</div>
                    </td>
                    <td className="text-sm">{j.organization_name}</td>
                    <td>
                      <Status status={j.status} />
                    </td>
                    <td className="tabular text-right">
                      {j.attempts}/{j.max_attempts}
                    </td>
                    <td className="whitespace-nowrap text-sm text-muted">{formatDateTime(j.created_at)}</td>
                    <td className="tabular whitespace-nowrap text-sm text-muted">
                      {j.started_at && j.finished_at ? `${((new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000).toFixed(1)} s` : "—"}
                    </td>
                    <td className="max-w-sm text-sm text-danger">{j.error ? <span className="line-clamp-2">{j.error}</span> : null}</td>
                    <td>
                      {["failed", "dead", "cancelled"].includes(j.status) ? (
                        <Button size="sm" onClick={() => retry.mutate(j)} disabled={retry.isPending}>
                          <RotateCw /> Retry
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </TBody>
            </Table>
          </Panel>
        )}
      </Section>
    </Main>
  );
}
