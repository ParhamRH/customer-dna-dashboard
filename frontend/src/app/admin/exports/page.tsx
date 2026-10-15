"use client";
import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Download, PackagePlus } from "lucide-react";
import { toast } from "sonner";
import { request, errorMessage } from "@/lib/api";
import { useCustomers } from "@/lib/admin";
import { formatBytes, formatDateTime, formatNumber, humanize, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/input";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Field } from "@/components/ui/label";
import { Status } from "@/components/status";
import { NewExportDialog, openSignedDownload } from "@/components/manage/exports";

type Row = {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  mode: "full" | "selective";
  status: string;
  brand_names: string[];
  domains: string[];
  include_originals: boolean | null;
  file_count: number | null;
  size_bytes: number | null;
  archive_checksum: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
  download_available: boolean;
};

export default function AdminExports() {
  const customers = useCustomers();
  const [org, setOrg] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [pick, setPick] = React.useState(false);
  const [target, setTarget] = React.useState("");
  const [dialogOrg, setDialogOrg] = React.useState<string | null>(null);
  const q = useQuery({
    queryKey: ["admin", "exports", org, status],
    queryFn: () => request<{ items: Row[]; imports: { id: string; organization_name: string; status: string; filename: string | null; created_at: string }[] }>(
      "/v1/platform/exports",
      { params: { organization_id: org || undefined, status: status || undefined } },
    ),
    refetchInterval: (query) => (query.state.data?.items.some((e) => e.status === "queued" || e.status === "running") ? 2000 : 15000),
  });

  return (
    <Main wide>
      <PageHeader
        title="Export management"
        description="Every customer's exports in one place. An export only ever contains the data of the customer it was created for."
        actions={
          <Button variant="primary" onClick={() => setPick(true)}>
            <PackagePlus /> Export a customer library
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <NativeSelect aria-label="Customer" className="w-60" value={org} onChange={(e) => setOrg(e.target.value)}>
          <option value="">All customers</option>
          {customers.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {["queued", "running", "completed", "failed", "expired"].map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </NativeSelect>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {!q.data ? (
        <LoadingBlock rows={5} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No exports match">Create one with “Export a customer library”.</EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Requested</th>
                <th>Customer</th>
                <th>Brand</th>
                <th>Mode</th>
                <th>Domains</th>
                <th className="text-right">Files</th>
                <th className="text-right">Size</th>
                <th>Status</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap text-sm">{formatDateTime(e.created_at)}</td>
                  <td>
                    <Link className="hover:underline" href={`/admin/customers/${e.organization_id}`}>
                      {e.organization_name}
                    </Link>
                  </td>
                  <td className="text-sm">{e.brand_names.join(", ")}</td>
                  <td className="text-sm">{e.mode === "full" ? "Complete library" : "Selective"}</td>
                  <td className="text-sm text-muted">{e.mode === "full" ? "All" : e.domains.map(humanize).join(", ") || "Selection"}</td>
                  <td className="tabular text-right">{formatNumber(e.file_count)}</td>
                  <td className="tabular text-right">{formatBytes(e.size_bytes)}</td>
                  <td>
                    <Status status={e.status} />
                    {e.status === "completed" && e.expires_at ? <div className="text-xs text-muted">until {formatDateTime(e.expires_at)}</div> : null}
                    {e.error ? <div className="max-w-56 truncate text-xs text-danger" title={e.error}>{e.error}</div> : null}
                  </td>
                  <td>
                    {e.download_available ? (
                      <Button size="sm" onClick={() => openSignedDownload(`/v1/exports/${e.id}/download`, e.organization_id).catch((err) => toast.error(errorMessage(err)))}>
                        <Download /> Download
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
      {q.data?.imports.length ? (
        <Section title="Recent imports" className="mt-10">
          <Panel>
            <Table>
              <THead>
                <tr>
                  <th>Uploaded</th>
                  <th>Into customer</th>
                  <th>Archive</th>
                  <th>Status</th>
                </tr>
              </THead>
              <TBody>
                {q.data.imports.map((i) => (
                  <tr key={i.id}>
                    <td className="text-sm">{relativeTime(i.created_at)}</td>
                    <td>{i.organization_name}</td>
                    <td className="text-sm text-muted">{i.filename}</td>
                    <td>
                      <Status status={i.status} />
                    </td>
                  </tr>
                ))}
              </TBody>
            </Table>
          </Panel>
        </Section>
      ) : null}
      <Dialog open={pick} onOpenChange={setPick}>
        <DialogContent size="sm">
          <DialogHeader title="Which customer?" description="The export is created inside that customer's workspace." />
          <DialogBody>
            <Field label="Customer" htmlFor="ex-cust">
              <NativeSelect id="ex-cust" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Choose…</option>
                {customers.data?.items
                  .filter((c) => c.status !== "pending_deletion")
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </NativeSelect>
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPick(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!target}
              onClick={() => {
                setPick(false);
                setDialogOrg(target);
              }}
            >
              Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {dialogOrg ? (
        <NewExportDialog
          org={dialogOrg}
          open
          onOpenChange={(o) => {
            if (!o) {
              setDialogOrg(null);
              q.refetch();
            }
          }}
        />
      ) : null}
    </Main>
  );
}
