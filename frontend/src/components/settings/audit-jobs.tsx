"use client";
import * as React from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import type { ActivityItem, Job, Page } from "@/lib/types";
import { JOB_LABELS, actionLabel } from "@/lib/labels";
import { formatDateTime, formatDuration, humanize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/input";
import { TBody, THead, Table } from "@/components/ui/misc";
import { EmptyState, LoadingBlock, Panel } from "@/components/page";
import { Status } from "@/components/status";

const PAGE = 50;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function Pager({ total, offset, setOffset }: { total: number; offset: number; setOffset: (n: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="flex items-center justify-end gap-2 text-sm text-muted">
      {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
      <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
        Previous
      </Button>
      <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
        Next
      </Button>
    </div>
  );
}

const AUDIT_FILTERS: [string, string][] = [
  ["", "All actions"],
  ["auth.", "Sign-ins"],
  ["member.", "Members"],
  ["api_token.", "API tokens"],
  ["integration.", "Integrations"],
  ["knowledge.", "Knowledge"],
  ["asset.", "Assets"],
  ["review.", "Review decisions"],
  ["export.", "Exports"],
  ["import.", "Imports"],
  ["brand.", "Brands & versions"],
];

export function AuditPanel() {
  const ws = useWorkspace();
  const [action, setAction] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const q = useQuery({
    queryKey: ws.key("audit", action, offset),
    queryFn: () => ws.req<Page<ActivityItem>>("/v1/workspace/audit-log", { params: { action: action || undefined, limit: PAGE, offset } }),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-base text-ink-2">Every change, decision and sign-in in this workspace. The log is append-only.</p>
        <NativeSelect
          aria-label="Filter actions"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setOffset(0);
          }}
          className="w-52"
        >
          {AUDIT_FILTERS.map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
      </div>
      {!q.data ? (
        <LoadingBlock rows={6} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="Nothing recorded">No entries match this filter.</EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Details</th>
                <th>IP</th>
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((a) => (
                <tr key={a.id}>
                  <td className="whitespace-nowrap text-sm text-muted">{formatDateTime(a.created_at)}</td>
                  <td className="max-w-[16rem] truncate text-sm" title={a.actor ?? undefined}>
                    {a.actor ?? (a.actor_type === "system" ? "System" : "—")}
                  </td>
                  <td className="text-sm">
                    {cap(actionLabel(a.action))}
                    <div className="font-mono text-[11px] text-faint">{a.action}</div>
                  </td>
                  <td className="max-w-[28rem] truncate font-mono text-[11px] text-muted" title={JSON.stringify(a.details)}>
                    {a.details && Object.keys(a.details as object).length ? JSON.stringify(a.details) : ""}
                  </td>
                  <td className="font-mono text-[11px] text-faint">{a.ip_address ?? ""}</td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
      {q.data ? <Pager total={q.data.total} offset={offset} setOffset={setOffset} /> : null}
    </div>
  );
}

const JOB_FILTERS: [string, string][] = [
  ["", "All jobs"],
  ["failed,dead", "Failed"],
  ["queued,running", "Queued or running"],
  ["succeeded", "Succeeded"],
];

export function JobsPanel() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [status, setStatus] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const key = ws.key("jobs", status, offset);
  const q = useQuery({
    queryKey: key,
    queryFn: () => ws.req<Page<Job>>("/v1/jobs", { params: { status: status ? status.split(",") : undefined, limit: PAGE, offset } }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((j) => j.status === "queued" || j.status === "running") ? 3000 : false),
  });
  const act = useMutation({
    mutationFn: ({ id, op }: { id: string; op: "retry" | "cancel" }) => ws.req(`/v1/jobs/${id}/${op}`, { method: "POST" }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ws.key("jobs") });
      toast.success(v.op === "retry" ? "Job queued again" : "Job cancelled");
    },
  });
  const can = ws.can("jobs.manage");
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-base text-ink-2">Background work for this workspace: media processing, AI analysis, embeddings, exports and webhook deliveries.</p>
        <NativeSelect
          aria-label="Filter jobs"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className="w-52"
        >
          {JOB_FILTERS.map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
      </div>
      {!q.data ? (
        <LoadingBlock rows={6} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No jobs">Nothing matches this filter.</EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Queued</th>
                <th>Duration</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((j) => {
                const ms = j.started_at && j.finished_at ? new Date(j.finished_at).getTime() - new Date(j.started_at).getTime() : null;
                return (
                  <tr key={j.id}>
                    <td>
                      <div className="text-sm font-medium">{JOB_LABELS[j.job_type] ?? humanize(j.job_type)}</div>
                      {j.error ? (
                        <div className="max-w-[32rem] truncate font-mono text-[11px] text-danger" title={j.error}>
                          {j.error}
                        </div>
                      ) : j.entity_type ? (
                        <div className="text-xs text-muted">{humanize(j.entity_type)}</div>
                      ) : null}
                    </td>
                    <td>
                      <Status status={j.status} label={j.status === "running" && j.progress ? `Running · ${j.progress}%` : undefined} />
                    </td>
                    <td className="tabular text-sm">
                      {j.attempts}/{j.max_attempts}
                    </td>
                    <td className="whitespace-nowrap text-sm text-muted">{formatDateTime(j.created_at)}</td>
                    <td className="tabular text-sm text-muted">{ms != null ? (ms < 1000 ? `${ms} ms` : formatDuration(ms / 1000)) : "—"}</td>
                    <td>
                      {can && ["failed", "dead", "cancelled"].includes(j.status) ? (
                        <Button size="sm" disabled={act.isPending} onClick={() => act.mutate({ id: j.id, op: "retry" })}>
                          Retry
                        </Button>
                      ) : can && j.status === "queued" ? (
                        <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => act.mutate({ id: j.id, op: "cancel" })}>
                          Cancel
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        </Panel>
      )}
      {q.data ? <Pager total={q.data.total} offset={offset} setOffset={setOffset} /> : null}
    </div>
  );
}
