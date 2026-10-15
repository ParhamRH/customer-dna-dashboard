"use client";
import * as React from "react";
import Link from "next/link";
import { ExternalLink, Plus, Search } from "lucide-react";
import { useCustomers } from "@/lib/admin";
import { cn, formatBytes, formatNumber, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { Meter, TBody, THead, Table } from "@/components/ui/misc";
import { Status } from "@/components/status";
import { DnaStrip } from "@/components/dna-strip";
import { NewCustomerDialog } from "@/components/admin/new-customer";

type StatusFilter = "all" | "active" | "archived" | "pending_deletion";

export default function CustomersPage() {
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [status, setStatus] = React.useState<StatusFilter>("all");
  const [newOpen, setNewOpen] = React.useState(false);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  const q = useCustomers({ search: debounced || undefined, status: status === "all" ? undefined : status });
  const rows = q.data?.items ?? [];

  return (
    <Main wide>
      <PageHeader
        title="Customers"
        description="Each customer has an isolated workspace and brand library. Open a workspace to work inside it."
        actions={
          <Button variant="primary" onClick={() => setNewOpen(true)}>
            <Plus /> New customer
          </Button>
        }
      />
      <NewCustomerDialog open={newOpen} onOpenChange={setNewOpen} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name or address" className="pl-8" aria-label="Search customers" />
        </div>
        <Segmented<StatusFilter>
          label="Status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "All" },
            { value: "active", label: "Active" },
            { value: "archived", label: "Archived" },
            { value: "pending_deletion", label: "Pending deletion" },
          ]}
        />
        <span className="ml-auto text-sm text-muted">{q.data ? `${q.data.total} shown` : ""}</span>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {q.isLoading ? (
        <LoadingBlock rows={4} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={debounced || status !== "all" ? "No customers match" : "No customers yet"}
          action={
            debounced || status !== "all" ? undefined : (
              <Button variant="primary" onClick={() => setNewOpen(true)}>
                <Plus /> Create the first customer
              </Button>
            )
          }
        >
          {debounced || status !== "all" ? "Try a different search or status." : "Create a customer to give them an isolated brand library."}
        </EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th className="w-[26%]">Customer</th>
                <th className="w-[16%]">Palette</th>
                <th>Status</th>
                <th className="text-right">Members</th>
                <th className="text-right">Assets</th>
                <th className="w-[13%]">Storage</th>
                <th className="text-right">To review</th>
                <th>Last activity</th>
                <th className="w-0">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </THead>
            <TBody>
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-surface-2">
                  <td>
                    <Link href={`/admin/customers/${c.id}`} className="font-medium text-ink hover:underline">
                      {c.name}
                    </Link>
                    <div className="text-sm text-muted">{[c.industry, c.country].filter(Boolean).join(", ") || c.slug}</div>
                  </td>
                  <td>
                    <DnaStrip
                      colors={c.palette.map((p) => ({ hex: p.hex, name: p.name, weight: p.role === "primary" ? 3 : 1 }))}
                      height={10}
                      interactive
                      label={c.name}
                    />
                  </td>
                  <td>
                    <Status status={c.status} />
                  </td>
                  <td className="tabular text-right">{formatNumber(c.member_count)}</td>
                  <td className="tabular text-right">{formatNumber(c.asset_count)}</td>
                  <td>
                    <div className="tabular text-sm">
                      {formatBytes(c.storage_bytes)}
                      {c.storage_quota_bytes ? <span className="text-muted"> of {formatBytes(c.storage_quota_bytes)}</span> : null}
                    </div>
                    {c.storage_quota_bytes ? (
                      <Meter
                        className="mt-1"
                        value={c.storage_bytes}
                        max={c.storage_quota_bytes}
                        tone={c.storage_bytes / c.storage_quota_bytes > 0.9 ? "danger" : "ink"}
                        label={`${c.name} storage`}
                      />
                    ) : null}
                  </td>
                  <td className={cn("tabular text-right", c.pending_reviews ? "text-ai" : "text-muted")}>{formatNumber(c.pending_reviews)}</td>
                  <td className="whitespace-nowrap text-sm text-muted">{relativeTime(c.last_activity_at)}</td>
                  <td>
                    {c.status !== "pending_deletion" ? (
                      <Button size="sm" variant="secondary" asChild>
                        <Link href={`/w/${c.slug}`}>
                          Open <ExternalLink />
                        </Link>
                      </Button>
                    ) : null}
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
