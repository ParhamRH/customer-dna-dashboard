"use client";
import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Copy, Download, FileArchive, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useAssetPicker, useCollections, useConcepts, useProjects, useRegistry } from "@/lib/hooks";
import { downloadFrom, errorMessage } from "@/lib/api";
import type { ContextPackage, ContextPreview, ContextTemplate } from "@/lib/types";
import { CLASSIFICATIONS, ENTITY_LABELS, PROJECT_TYPE_LABELS } from "@/lib/labels";
import { cn, copyText, formatDateTime, formatNumber, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, MetaList, PageHeader, Panel, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogBody, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { AssetThumb } from "@/components/asset-thumb";
import { Markdown } from "@/components/markdown";
import { StatusMark, Tag } from "@/components/status";
import { CopyValue } from "@/components/code-block";

type Mode = "compact" | "standard" | "comprehensive";
type Req = {
  task_type: string;
  project_id: string;
  output_medium: string;
  mode: Mode;
  title: string;
  domains: string[];
  concept_ids: string[];
  creative_direction: string;
  reference_asset_ids: string[];
  collection_ids: string[];
  auto_references: boolean;
  use_published_version: boolean;
};

const STEPS = ["Task", "Direction & scope", "Review what is included", "Package"];
const MODE_COPY: Record<Mode, string> = {
  compact: "The essentials: top principles, a few concepts and references. Fits a short prompt.",
  standard: "A complete brief for most creative tasks.",
  comprehensive: "Everything relevant, with full documents. For agents that read long context.",
};

function body(ws: ReturnType<typeof useWorkspace>, r: Req) {
  return {
    brand_id: ws.brand.id,
    task_type: r.task_type,
    project_id: r.project_id || null,
    output_medium: r.output_medium || null,
    mode: r.mode,
    domains: r.domains.length ? r.domains : null,
    concept_ids: r.concept_ids,
    creative_direction: r.creative_direction || null,
    reference_asset_ids: r.reference_asset_ids,
    collection_ids: r.collection_ids,
    auto_references: r.auto_references,
    use_published_version: r.use_published_version,
    title: r.title || null,
  };
}

function Stepper({ step, setStep, maxStep }: { step: number; setStep: (n: number) => void; maxStep: number }) {
  return (
    <ol className="mb-8 flex flex-wrap gap-x-6 gap-y-2 border-b border-line pb-3" aria-label="Steps">
      {STEPS.map((s, i) => (
        <li key={s}>
          <button
            disabled={i > maxStep}
            onClick={() => setStep(i)}
            aria-current={i === step ? "step" : undefined}
            className={cn("flex items-center gap-2 text-base disabled:cursor-not-allowed disabled:opacity-40", i === step ? "font-semibold text-ink" : "text-muted hover:text-ink")}
          >
            <span className={cn("tabular flex size-6 items-center justify-center rounded-full border text-xs", i === step ? "border-ink bg-ink text-paper" : i < step ? "border-accent text-accent" : "border-line-strong")}>{i + 1}</span>
            {s}
          </button>
        </li>
      ))}
    </ol>
  );
}

function TaskStep({ r, set, templates }: { r: Req; set: (p: Partial<Req>) => void; templates: ContextTemplate[] }) {
  const projects = useProjects();
  return (
    <div className="grid gap-6">
      <div role="radiogroup" aria-label="Task type" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {templates.map((t) => (
          <button
            key={t.key}
            role="radio"
            aria-checked={r.task_type === t.key}
            onClick={() => set({ task_type: t.key, domains: t.domains })}
            className={cn("grid gap-1 rounded-lg border p-3 text-left transition-colors", r.task_type === t.key ? "border-ink bg-surface" : "border-line bg-surface-2 hover:border-line-strong")}
          >
            <span className="font-medium">{t.label}</span>
            <span className="line-clamp-2 text-sm text-muted">{t.instructions[0]}</span>
            {t.include_tokens ? <span className="text-xs text-muted">Includes design tokens</span> : null}
          </button>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Project" htmlFor="cx-proj" hint="Adds the project's brief, objectives and reference assets.">
          <NativeSelect
            id="cx-proj"
            value={r.project_id}
            onChange={(e) => {
              const p = projects.data?.items.find((x) => x.id === e.target.value);
              set({ project_id: e.target.value, ...(p?.selected_domains.length ? { domains: p.selected_domains } : {}) });
            }}
          >
            <option value="">No project</option>
            {projects.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} — {PROJECT_TYPE_LABELS[p.project_type]}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Output medium" htmlFor="cx-medium" hint="e.g. Instagram carousel, landing page, 30-second film">
          <Input id="cx-medium" value={r.output_medium} onChange={(e) => set({ output_medium: e.target.value })} />
        </Field>
        <Field label="Package title" htmlFor="cx-title" hint="Optional. Defaults to brand, task and mode.">
          <Input id="cx-title" value={r.title} onChange={(e) => set({ title: e.target.value })} />
        </Field>
      </div>
      <div className="grid gap-2">
        <Label>Depth</Label>
        <div role="radiogroup" aria-label="Depth" className="grid gap-2 sm:grid-cols-3">
          {(Object.keys(MODE_COPY) as Mode[]).map((m) => (
            <label key={m} className={cn("flex cursor-pointer items-start gap-2 rounded-md border p-3", r.mode === m ? "border-ink bg-surface" : "border-line")}>
              <input type="radio" name="mode" className="mt-1 accent-[var(--accent)]" checked={r.mode === m} onChange={() => set({ mode: m })} />
              <span>
                <span className="font-medium">{humanize(m)}</span>
                <span className="block text-sm text-muted">{MODE_COPY[m]}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

function DirectionStep({ r, set }: { r: Req; set: (p: Partial<Req>) => void }) {
  const registry = useRegistry();
  const concepts = useConcepts();
  const collections = useCollections();
  const [q, setQ] = React.useState("");
  const assets = useAssetPicker(q);
  const toggle = (k: "domains" | "concept_ids" | "reference_asset_ids" | "collection_ids", v: string) => set({ [k]: r[k].includes(v) ? r[k].filter((x) => x !== v) : [...r[k], v] } as Partial<Req>);
  const domains = (registry.data?.domains ?? []).filter((d) => !["creative_assets", "ai_knowledge", "projects_applications", "principles_guidelines"].includes(d.key));
  return (
    <div className="grid gap-7">
      <div className="grid gap-2">
        <Label>Knowledge domains</Label>
        <p className="-mt-1 text-sm text-muted">Preselected by the task. Principles that apply to the task are always included, whatever their domain.</p>
        <div className="grid gap-1.5 sm:grid-cols-3">
          {domains.map((d) => (
            <label key={d.key} className="flex items-center gap-2 text-base">
              <Checkbox checked={r.domains.includes(d.key)} onCheckedChange={() => toggle("domains", d.key)} /> {d.name}
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Aesthetic concepts to emphasise</Label>
        <div className="flex flex-wrap gap-1.5">
          {(concepts.data?.items ?? [])
            .filter((c) => c.status === "approved" && c.brand_relevance !== "avoid")
            .map((c) => {
              const on = r.concept_ids.includes(c.id);
              return (
                <button key={c.id} aria-pressed={on} onClick={() => toggle("concept_ids", c.id)} className={cn("h-7 rounded-full border px-3 text-sm", on ? "border-ink bg-ink text-paper" : "border-line-strong hover:bg-sunken")}>
                  {c.name}
                </button>
              );
            })}
        </div>
        <p className="text-sm text-muted">Concepts marked “avoid” are always listed as prohibited directions.</p>
      </div>
      <Field label="Creative direction" htmlFor="cx-dir" hint="Your brief in your own words. Passed to the AI as the task-specific direction.">
        <Textarea id="cx-dir" rows={3} value={r.creative_direction} onChange={(e) => set({ creative_direction: e.target.value })} placeholder="e.g. Launch of the winter ritual collection — warmer light, same calm." />
      </Field>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Label>Reference assets</Label>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <Switch checked={r.auto_references} onCheckedChange={(v) => set({ auto_references: v })} /> Also pick approved references automatically
          </label>
        </div>
        <Input placeholder="Search the asset library" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search reference assets" />
        <div className="grid max-h-72 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-6 lg:grid-cols-8">
          {(assets.data?.items ?? []).map((a) => {
            const on = r.reference_asset_ids.includes(a.id);
            return (
              <button key={a.id} onClick={() => toggle("reference_asset_ids", a.id)} aria-pressed={on} title={a.title} className="text-left">
                <AssetThumb asset={a} className={cn("aspect-square rounded", on && "ring-2 ring-accent ring-offset-2 ring-offset-paper")} showDuration={false} />
                <span className="mt-0.5 block truncate text-[11px] text-muted">{a.title}</span>
              </button>
            );
          })}
        </div>
        {collections.data?.items.length ? (
          <div className="flex flex-wrap gap-3">
            {collections.data.items.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm">
                <Checkbox checked={r.collection_ids.includes(c.id)} onCheckedChange={() => toggle("collection_ids", c.id)} /> {c.name} <span className="text-muted">{c.asset_count}</span>
              </label>
            ))}
          </div>
        ) : null}
      </div>
      <label className="flex items-center gap-2 text-base">
        <Switch checked={r.use_published_version} onCheckedChange={(v) => set({ use_published_version: v })} /> Use the published brand version instead of the latest approved knowledge
      </label>
    </div>
  );
}

function PreviewStep({ preview }: { preview: ContextPreview }) {
  const order = ["principle", "guideline", "knowledge_entry", "aesthetic_concept", "palette", "typography_system", "design_token", "asset", "project"];
  return (
    <div className="grid gap-8">
      <Panel className="grid grid-cols-2 gap-5 p-5 sm:grid-cols-4">
        <div>
          <p className="text-sm text-muted">Sources</p>
          <p className="text-xl font-semibold">{formatNumber(Object.values(preview.counts).reduce((a, b) => a + b, 0))}</p>
        </div>
        <div>
          <p className="text-sm text-muted">Mandatory rules</p>
          <p className="text-xl font-semibold">{preview.principles_by_classification.mandatory ?? 0}</p>
        </div>
        <div>
          <p className="text-sm text-muted">Prohibited directions</p>
          <p className="text-xl font-semibold">{preview.prohibited_count}</p>
        </div>
        <div>
          <p className="text-sm text-muted">Brand version</p>
          <p className="text-xl font-semibold">{preview.brand_version ? `v${preview.brand_version}` : "Latest approved"}</p>
        </div>
      </Panel>
      <Section title="Principles by classification">
        <div className="flex flex-wrap gap-2">
          {CLASSIFICATIONS.filter((c) => preview.principles_by_classification[c.key]).map((c) => (
            <Tag key={c.key} tone="outline">
              {c.label} {preview.principles_by_classification[c.key]}
            </Tag>
          ))}
        </div>
      </Section>
      {preview.references.length ? (
        <Section title="Visual references" description="Why each reference was chosen. Only approved interpretations describe them.">
          <ul className="grid gap-2">
            {preview.references.map((r) => (
              <li key={r.id} className="flex flex-wrap items-baseline gap-x-3 text-base">
                <span className="font-medium">{r.title}</span>
                <span className="text-sm text-muted">{r.selected_because}</span>
                <span className="text-xs text-muted">interpretation: {humanize(r.interpretation_status)}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section title="Every source, with its version" description="The package cites these identifiers so each statement can be traced back.">
        <div className="grid gap-5 sm:grid-cols-2">
          {order
            .filter((t) => preview.sources[t]?.length)
            .map((t) => (
              <div key={t}>
                <p className="mb-1 text-sm font-medium">
                  {ENTITY_LABELS[t] ?? humanize(t)} <span className="text-muted">{preview.sources[t].length}</span>
                </p>
                <ul className="grid gap-0.5">
                  {preview.sources[t].map((s) => (
                    <li key={s.ref} className="flex items-center gap-2 text-sm">
                      <StatusMark status={s.status ?? "approved"} />
                      <span className="truncate">{s.label}</span>
                      {s.version ? <span className="text-xs text-faint">v{s.version}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        </div>
      </Section>
    </div>
  );
}

function PackageView({ pkg }: { pkg: ContextPackage }) {
  const ws = useWorkspace();
  const md = pkg.markdown ?? pkg.content_markdown ?? "";
  const slug = `context-${pkg.task_type}-${pkg.id.slice(0, 8)}`;
  const dl = (format: "md" | "json" | "yaml" | "zip") =>
    downloadFrom(`/v1/context/packages/${pkg.id}/download`, `${slug}.${format}`, ws.orgId, { format }).catch((e) => toast.error(errorMessage(e)));
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <Panel className="min-w-0 p-6">
        <Markdown className="max-w-none font-sans text-md [&_h1]:text-2xl">{md}</Markdown>
      </Panel>
      <aside className="grid content-start gap-5">
        <div className="grid gap-2">
          <Button
            variant="primary"
            onClick={async () => {
              if (await copyText(md)) toast.success("Markdown copied — paste it into your AI tool");
            }}
          >
            <Copy /> Copy as Markdown
          </Button>
          <div className="grid grid-cols-3 gap-2">
            <Button size="sm" onClick={() => dl("md")}>
              <Download /> MD
            </Button>
            <Button size="sm" onClick={() => dl("json")}>
              JSON
            </Button>
            <Button size="sm" onClick={() => dl("yaml")}>
              YAML
            </Button>
          </div>
          <Button size="sm" onClick={() => dl("zip")}>
            <FileArchive /> ZIP with reference media
          </Button>
        </div>
        <MetaList
          className="text-sm"
          items={[
            ["Task", humanize(pkg.task_type)],
            ["Mode", humanize(pkg.mode)],
            ["Medium", pkg.output_medium],
            ["Size", `≈ ${formatNumber(pkg.token_estimate)} tokens`],
            ["Sources", pkg.sources?.length],
            ["Checksum", <CopyValue key="c" value={pkg.checksum} display={pkg.checksum.slice(0, 12) + "…"} />],
            ["Created", formatDateTime(pkg.created_at)],
          ]}
        />
      </aside>
    </div>
  );
}

function SavedPackages({ onOpen }: { onOpen: (id: string) => void }) {
  const ws = useWorkspace();
  const q = useQuery({ queryKey: ws.key("context", "packages", ws.brand.id), queryFn: () => ws.req<{ items: ContextPackage[] }>("/v1/context/packages", { params: { brand_id: ws.brand.id } }) });
  if (!q.data?.items.length) return null;
  return (
    <Section title="Saved packages" className="mt-12">
      <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
        {q.data.items.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-base">
            <button className="font-medium hover:underline" onClick={() => onOpen(p.id)}>
              {p.title}
            </button>
            <span className="text-sm text-muted">
              {humanize(p.mode)} · ≈ {formatNumber(p.token_estimate)} tokens
            </span>
            <span className="ml-auto text-sm text-muted">{formatDateTime(p.created_at)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export default function ContextGenerator() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const templates = useQuery({ queryKey: ws.key("context", "templates"), queryFn: () => ws.req<{ templates: ContextTemplate[] }>("/v1/context/templates") });
  const [step, setStep] = React.useState(0);
  const [r, setR] = React.useState<Req>({
    task_type: "website_design",
    project_id: params.get("project") ?? "",
    output_medium: "",
    mode: "standard",
    title: "",
    domains: [],
    concept_ids: params.get("concept") ? [params.get("concept")!] : [],
    creative_direction: "",
    reference_asset_ids: [],
    collection_ids: params.get("collection") ? [params.get("collection")!] : [],
    auto_references: true,
    use_published_version: false,
  });
  const [openPkg, setOpenPkg] = React.useState<string | null>(null);
  // Preselect the task template's domains once templates have loaded.
  if (templates.data && !r.domains.length) {
    const t = templates.data.templates.find((x) => x.key === r.task_type);
    if (t?.domains.length) setR({ ...r, domains: t.domains });
  }
  const set = (p: Partial<Req>) => setR((x) => ({ ...x, ...p }));
  const preview = useMutation({ mutationFn: () => ws.req<ContextPreview>("/v1/context/preview", { method: "POST", body: body(ws, r) }) });
  const generate = useMutation({ mutationFn: () => ws.req<ContextPackage>("/v1/context/generate", { method: "POST", body: body(ws, r) }) });
  const saved = useQuery({
    queryKey: ws.key("context", "package", openPkg),
    queryFn: () => ws.req<ContextPackage>(`/v1/context/packages/${openPkg}`),
    enabled: !!openPkg,
  });
  const canGenerate = ws.can("context.generate");
  const maxStep = generate.data ? 3 : preview.data ? 2 : 1;

  if (templates.error) return <Main><ErrorState error={templates.error} /></Main>;
  if (!templates.data) return <Main><LoadingBlock rows={6} /></Main>;
  return (
    <Main wide>
      <PageHeader
        title="Context generator"
        description="Build a task-specific brand brief for an AI model or a designer: the right rules, language, visual system and references — every statement traceable to its source."
      />
      <Stepper step={step} setStep={setStep} maxStep={maxStep} />
      {step === 0 ? <TaskStep r={r} set={set} templates={templates.data.templates} /> : null}
      {step === 1 ? <DirectionStep r={r} set={set} /> : null}
      {step === 2 ? preview.isPending ? <LoadingBlock rows={6} /> : preview.error ? <ErrorState error={preview.error} /> : preview.data ? <PreviewStep preview={preview.data} /> : null : null}
      {step === 3 ? generate.isPending ? <LoadingBlock rows={8} /> : generate.error ? <ErrorState error={generate.error} /> : generate.data ? <PackageView pkg={generate.data} /> : null : null}

      <div className="mt-10 flex flex-wrap items-center gap-3 border-t border-line pt-5">
        {step > 0 ? (
          <Button onClick={() => setStep(step - 1)}>
            <ArrowLeft /> Back
          </Button>
        ) : null}
        {step < 2 ? (
          <Button
            variant="primary"
            onClick={() => {
              if (step === 1) {
                preview.mutate();
                setStep(2);
              } else setStep(1);
            }}
          >
            {step === 1 ? "Preview what is included" : "Next"} <ArrowRight />
          </Button>
        ) : null}
        {step === 2 && preview.data ? (
          canGenerate ? (
            <Button
              variant="primary"
              disabled={generate.isPending}
              onClick={() => {
                generate.mutate();
                setStep(3);
              }}
            >
              <Sparkles /> Generate package
            </Button>
          ) : (
            <p className="text-sm text-muted">Your role can preview but not generate packages.</p>
          )
        ) : null}
        {step === 3 && generate.data ? (
          <Button
            onClick={() => {
              generate.reset();
              preview.reset();
              setStep(0);
            }}
          >
            Start another
          </Button>
        ) : null}
        <Link href={`${ws.base}/projects`} className="ml-auto text-sm text-muted hover:text-ink">
          Packages are saved with their project
        </Link>
      </div>
      <SavedPackages onOpen={setOpenPkg} />
      <Dialog open={!!openPkg} onOpenChange={(o) => !o && setOpenPkg(null)}>
        <DialogContent size="xl">
          <DialogHeader title={saved.data?.title ?? "Context package"} />
          <DialogBody>{saved.data ? <PackageView pkg={saved.data} /> : <LoadingBlock rows={6} />}</DialogBody>
        </DialogContent>
      </Dialog>
    </Main>
  );
}
