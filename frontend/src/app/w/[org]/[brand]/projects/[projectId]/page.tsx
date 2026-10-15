"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import type { Project } from "@/lib/types";
import { PROJECT_TYPE_LABELS } from "@/lib/labels";
import { formatDate, formatDateTime, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, MetaList, PageHeader, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Status } from "@/components/status";
import { AssetThumb } from "@/components/asset-thumb";
import { RelationshipsTab } from "@/components/knowledge/item-tabs";
import { ProjectDialog } from "@/components/projects/project-dialog";
import { useConfirm } from "@/components/confirm";
import { AssetPickerDialog } from "@/components/assets/picker";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const ws = useWorkspace();
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const [edit, setEdit] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const q = useQuery({ queryKey: ws.key("project", projectId), queryFn: () => ws.req<Project>(`/v1/projects/${projectId}`) });
  const addAssets = useMutation({
    mutationFn: (ids: string[]) => ws.req<Project>(`/v1/projects/${projectId}`, { method: "PATCH", body: { asset_ids: ids } }),
    onSuccess: (p) => {
      qc.setQueryData(ws.key("project", projectId), p);
      setAdding(false);
      toast.success("References added");
    },
  });
  const del = useMutation({
    mutationFn: () => ws.req(`/v1/projects/${projectId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("projects") });
      toast.success("Project deleted");
      router.push(`${ws.base}/projects`);
    },
  });
  if (q.error) return <Main><ErrorState error={q.error} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={8} /></Main>;
  const p = q.data;
  const can = ws.can("projects.manage");
  return (
    <Main>
      <Link href={`${ws.base}/projects`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-3.5" /> Projects
      </Link>
      <PageHeader
        title={p.name}
        meta={
          <>
            <span>{PROJECT_TYPE_LABELS[p.project_type]}</span>
            <Status status={p.status} label={humanize(p.status)} />
            {p.start_date || p.due_date ? <span>{formatDate(p.start_date)} – {formatDate(p.due_date)}</span> : null}
          </>
        }
        actions={
          <>
            {ws.can("context.generate") ? (
              <Button variant="primary" asChild>
                <Link href={`${ws.base}/context?project=${p.id}`}>
                  <Sparkles /> Generate context
                </Link>
              </Button>
            ) : null}
            {can ? (
              <>
                <Button onClick={() => setEdit(true)}>
                  <Pencil /> Edit
                </Button>
                <Button
                  variant="ghost"
                  aria-label="Delete project"
                  onClick={async () => {
                    if (await confirm({ title: `Delete ${p.name}?`, description: "The project and its links are removed. Assets and knowledge are not affected.", confirmLabel: "Delete project", destructive: true })) del.mutate();
                  }}
                >
                  <Trash2 />
                </Button>
              </>
            ) : null}
          </>
        }
      />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <Section title="Brief">
            {p.description ? <p className="mb-4 max-w-3xl text-md">{p.description}</p> : null}
            <MetaList
              items={[
                ["Objectives", p.objectives],
                ["Audience", p.audience],
                ["Deliverables", p.deliverables?.length ? <ul key="d" className="list-disc pl-4">{p.deliverables.map((d, i) => <li key={i}>{String(d)}</li>)}</ul> : null],
                ["Domains", p.selected_domains.length ? p.selected_domains.map(humanize).join(", ") : "Chosen by the task template"],
              ]}
            />
          </Section>
          <Section
            title="Reference assets"
            actions={
              can ? (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <Plus /> Add
                </Button>
              ) : undefined
            }
          >
            {p.assets?.length ? (
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
                {p.assets.map((a) => (
                  <Link key={a.id} href={`${ws.base}/assets/${a.id}`} className="group">
                    <AssetThumb asset={a} className="aspect-square rounded-md" />
                    <span className="mt-1 block truncate text-xs text-muted group-hover:text-ink">{a.title}</span>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No reference assets yet.</p>
            )}
          </Section>
          <Section title="Relationships" description="Concepts, principles and assets connected to this project.">
            <RelationshipsTab entityType="project" entityId={p.id} relationships={p.relationships ?? []} canEdit={ws.can("knowledge.write")} />
          </Section>
        </div>
        <aside>
          <Section title="Context packages">
            {p.context_packages?.length ? (
              <ul className="grid gap-2">
                {p.context_packages.map((c) => (
                  <li key={c.id} className="text-sm">
                    <Link href={`${ws.base}/context`} className="font-medium hover:underline">
                      {c.title}
                    </Link>
                    <div className="text-muted">
                      {humanize(c.mode)} · {formatDateTime(c.created_at)}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">None yet. Generate one for this project.</p>
            )}
          </Section>
        </aside>
      </div>
      <ProjectDialog project={p} open={edit} onOpenChange={setEdit} />
      <AssetPickerDialog
        open={adding}
        onOpenChange={setAdding}
        title={`Reference assets for ${p.name}`}
        description="Linked to the project with a “uses” relationship, and offered as references when you generate context for it."
        confirmLabel="Add references"
        exclude={(p.assets ?? []).map((a) => a.id)}
        pending={addAssets.isPending}
        onConfirm={(ids) => addAssets.mutate(ids)}
      />
    </Main>
  );
}
