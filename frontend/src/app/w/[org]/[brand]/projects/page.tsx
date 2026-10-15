"use client";
import * as React from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useWorkspace } from "@/lib/workspace";
import { useProjects } from "@/lib/hooks";
import { PROJECT_TYPE_LABELS } from "@/lib/labels";
import { formatDate, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Status } from "@/components/status";
import { ProjectDialog } from "@/components/projects/project-dialog";

export default function ProjectsPage() {
  const ws = useWorkspace();
  const q = useProjects();
  const [open, setOpen] = React.useState(false);
  return (
    <Main>
      <PageHeader
        title="Projects"
        description="Creative work for this brand — a website, a campaign, packaging. Each project picks the knowledge that matters and keeps its context packages."
        actions={
          ws.can("projects.manage") ? (
            <Button variant="primary" onClick={() => setOpen(true)}>
              <Plus /> New project
            </Button>
          ) : undefined
        }
      />
      {q.error ? <ErrorState error={q.error} /> : null}
      {!q.data ? (
        <LoadingBlock rows={4} />
      ) : q.data.items.length === 0 ? (
        <EmptyState title="No projects yet">Create a project to collect references and generate a brief for it.</EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Project</th>
                <th>Type</th>
                <th>Status</th>
                <th>Domains</th>
                <th>Due</th>
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((p) => (
                <tr key={p.id} className="hover:bg-surface-2">
                  <td>
                    <Link href={`${ws.base}/projects/${p.id}`} className="font-medium hover:underline">
                      {p.name}
                    </Link>
                    {p.description ? <div className="line-clamp-1 text-sm text-muted">{p.description}</div> : null}
                  </td>
                  <td className="text-sm">{PROJECT_TYPE_LABELS[p.project_type]}</td>
                  <td>
                    <Status status={p.status} label={humanize(p.status)} />
                  </td>
                  <td className="text-sm text-muted">{p.selected_domains.length ? p.selected_domains.map(humanize).join(", ") : "From task template"}</td>
                  <td className="whitespace-nowrap text-sm text-muted">{formatDate(p.due_date)}</td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
      <ProjectDialog project={null} open={open} onOpenChange={setOpen} />
    </Main>
  );
}
