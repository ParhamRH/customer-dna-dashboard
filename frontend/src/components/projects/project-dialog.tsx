"use client";
import * as React from "react";
import { useResetState } from "@/lib/state";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import { useConcepts, usePrinciples, useRegistry } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { Project } from "@/lib/types";
import { PROJECT_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";

export function ProjectDialog({ project, open, onOpenChange }: { project: Project | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const router = useRouter();
  const registry = useRegistry();
  const concepts = useConcepts();
  const principles = usePrinciples();
  const blank = { name: "", project_type: "website_design", status: "planning", description: "", objectives: "", audience: "", deliverables: "", start_date: "", due_date: "", selected_domains: [] as string[], concept_ids: [] as string[], principle_ids: [] as string[] };
  const [f, setF] = useResetState([open, project?.id], () =>
      project
        ? {
            name: project.name,
            project_type: project.project_type,
            status: project.status,
            description: project.description ?? "",
            objectives: project.objectives ?? "",
            audience: project.audience ?? "",
            deliverables: (project.deliverables ?? []).map(String).join("\n"),
            start_date: project.start_date ?? "",
            due_date: project.due_date ?? "",
            selected_domains: project.selected_domains,
            concept_ids: [],
            principle_ids: [],
          }
        : blank,
  );
  const save = useMutation({
    mutationFn: () => {
      const b = {
        name: f.name,
        project_type: f.project_type,
        status: f.status,
        description: f.description || null,
        objectives: f.objectives || null,
        audience: f.audience || null,
        deliverables: f.deliverables.split("\n").map((x) => x.trim()).filter(Boolean),
        start_date: f.start_date || null,
        due_date: f.due_date || null,
        selected_domains: f.selected_domains,
        ...(f.concept_ids.length ? { concept_ids: f.concept_ids } : {}),
        ...(f.principle_ids.length ? { principle_ids: f.principle_ids } : {}),
      };
      return project ? ws.req<Project>(`/v1/projects/${project.id}`, { method: "PATCH", body: b }) : ws.req<Project>(`/v1/brands/${ws.brand.id}/projects`, { method: "POST", body: b });
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ws.key("projects") });
      qc.invalidateQueries({ queryKey: ws.key("project") });
      toast.success(project ? "Project saved" : "Project created");
      onOpenChange(false);
      if (!project) router.push(`${ws.base}/projects/${p.id}`);
    },
    onError: () => {},
  });
  const linked = new Set((project?.relationships ?? []).map((r) => r.other_id));
  const toggle = (k: "selected_domains" | "concept_ids" | "principle_ids", v: string) => setF((s) => ({ ...s, [k]: s[k].includes(v) ? s[k].filter((x) => x !== v) : [...s[k], v] }));
  const domains = (registry.data?.domains ?? []).filter((d) => !["creative_assets", "ai_knowledge", "projects_applications"].includes(d.key));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader title={project ? `Edit ${project.name}` : "New project"} description="A project is a piece of creative work for this brand. It selects the knowledge that matters and collects its context packages." />
        <DialogBody className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name" htmlFor="pr-name" className="sm:col-span-3">
              <Input id="pr-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </Field>
            <Field label="Type" htmlFor="pr-type">
              <NativeSelect id="pr-type" value={f.project_type} onChange={(e) => setF({ ...f, project_type: e.target.value })}>
                {Object.entries(PROJECT_TYPE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Start" htmlFor="pr-start">
              <Input id="pr-start" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
            </Field>
            <Field label="Due" htmlFor="pr-due">
              <Input id="pr-due" type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
            </Field>
          </div>
          <Field label="Status" htmlFor="pr-status">
            <NativeSelect id="pr-status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} className="w-48">
              {["planning", "active", "completed", "archived"].map((s) => (
                <option key={s} value={s}>
                  {s[0].toUpperCase() + s.slice(1)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Description" htmlFor="pr-desc">
            <Textarea id="pr-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Objectives" htmlFor="pr-obj">
              <Textarea id="pr-obj" rows={3} value={f.objectives} onChange={(e) => setF({ ...f, objectives: e.target.value })} />
            </Field>
            <Field label="Audience" htmlFor="pr-aud">
              <Textarea id="pr-aud" rows={3} value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} />
            </Field>
          </div>
          <Field label="Deliverables" htmlFor="pr-del" hint="One per line">
            <Textarea id="pr-del" rows={3} value={f.deliverables} onChange={(e) => setF({ ...f, deliverables: e.target.value })} />
          </Field>
          <div className="grid gap-1.5">
            <Label>Relevant knowledge domains</Label>
            <div className="grid gap-1.5 sm:grid-cols-3">
              {domains.map((d) => (
                <label key={d.key} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={f.selected_domains.includes(d.key)} onCheckedChange={() => toggle("selected_domains", d.key)} /> {d.name}
                </label>
              ))}
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>{project ? "Link more concepts" : "Concepts the project uses"}</Label>
            <div className="flex flex-wrap gap-1.5">
              {(concepts.data?.items ?? []).filter((c) => c.status === "approved" && !linked.has(c.id)).map((c) => {
                const on = f.concept_ids.includes(c.id);
                return (
                  <button type="button" key={c.id} aria-pressed={on} onClick={() => toggle("concept_ids", c.id)} className={cn("h-6 rounded-full border px-2.5 text-sm", on ? "border-ink bg-ink text-paper" : "border-line-strong")}>
                    {c.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>{project ? "Apply more principles" : "Principles that apply"}</Label>
            <div className="grid max-h-36 gap-1 overflow-y-auto rounded-md border border-line p-2">
              {(principles.data?.items ?? []).filter((p) => p.status === "approved" && !linked.has(p.id)).map((p) => (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={f.principle_ids.includes(p.id)} onCheckedChange={() => toggle("principle_ids", p.id)} />
                  <span className="font-mono text-[11px] text-muted">{p.code}</span> {p.title}
                </label>
              ))}
            </div>
          </div>
          {save.error ? <p className="text-sm text-danger">{errorMessage(save.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.name || save.isPending} onClick={() => save.mutate()}>
            {project ? "Save project" : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
