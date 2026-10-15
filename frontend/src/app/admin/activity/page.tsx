"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { ActivityItem } from "@/lib/types";
import { useCustomers } from "@/lib/admin";
import { actionLabel } from "@/lib/labels";
import { formatDateTime, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/page";
import { Input, NativeSelect } from "@/components/ui/input";
import { TBody, THead, Table } from "@/components/ui/misc";

export default function ActivityPage() {
  const customers = useCustomers();
  const [org, setOrg] = React.useState("");
  const [filter, setFilter] = React.useState("");
  const [limit, setLimit] = React.useState(200);
  const q = useQuery({
    queryKey: ["admin", "activity", "log", org, limit],
    queryFn: () => request<{ items: ActivityItem[] }>("/v1/platform/activity", { params: { limit, organization_id: org || undefined } }),
    refetchInterval: 15000,
  });
  const f = filter.trim().toLowerCase();
  const rows = (q.data?.items ?? []).filter(
    (a) => !f || a.action.includes(f) || (a.actor ?? "").toLowerCase().includes(f) || actionLabel(a.action).includes(f),
  );
  return (
    <Main wide>
      <PageHeader
        title="System activity"
        description="The audit trail across every customer: sign-ins, approvals, uploads, exports and administrative changes. Entries cannot be edited."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <NativeSelect aria-label="Customer" className="w-60" value={org} onChange={(e) => setOrg(e.target.value)}>
          <option value="">All customers and platform</option>
          {customers.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        <Input className="w-64" placeholder="Filter by action or person" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter" />
        <NativeSelect aria-label="Entries" className="w-36" value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))}>
          {[100, 200, 500].map((n) => (
            <option key={n} value={n}>
              Last {n}
            </option>
          ))}
        </NativeSelect>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {!q.data ? (
        <LoadingBlock rows={8} />
      ) : rows.length === 0 ? (
        <EmptyState title="No matching activity" />
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>When</th>
                <th>Customer</th>
                <th>Who</th>
                <th>What</th>
                <th>Subject</th>
                <th>Details</th>
              </tr>
            </THead>
            <TBody>
              {rows.map((a) => (
                <tr key={a.id} className="align-top">
                  <td className="whitespace-nowrap text-sm text-muted">{formatDateTime(a.created_at)}</td>
                  <td className="text-sm">
                    {a.organization_id ? (
                      <Link href={`/admin/customers/${a.organization_id}`} className="hover:underline">
                        {a.organization_name}
                      </Link>
                    ) : (
                      <span className="text-muted">Platform</span>
                    )}
                  </td>
                  <td className="text-sm">{a.actor ?? humanize(a.actor_type)}</td>
                  <td>
                    <span className={a.action === "auth.login_failed" ? "text-danger" : ""}>{actionLabel(a.action)}</span>
                    <div className="font-mono text-[11px] text-faint">{a.action}</div>
                  </td>
                  <td className="text-sm text-muted">{a.entity_type ? `${humanize(a.entity_type)}` : "—"}</td>
                  <td className="max-w-md truncate font-mono text-[11px] text-muted" title={JSON.stringify(a.details)}>
                    {a.details && Object.keys(a.details).length ? JSON.stringify(a.details) : ""}
                  </td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
    </Main>
  );
}
