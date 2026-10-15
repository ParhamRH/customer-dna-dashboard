"use client";
import * as React from "react";
import type { Analysis, Json } from "@/lib/types";
import { cn, formatDateTime, humanize } from "@/lib/utils";
import { AiTag, Status, Tag } from "@/components/status";

function Chips({ items, tone = "default" }: { items?: unknown[]; tone?: "default" | "ai" }) {
  if (!items?.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((x, i) => (
        <Tag key={i} tone={tone === "ai" ? "default" : "default"}>
          {String(x).replace(/_/g, " ")}
        </Tag>
      ))}
    </div>
  );
}

/** Measured, objective properties (what the machine saw), rendered compactly. */
export function ObjectiveView({ data }: { data: Json }) {
  const rows: [string, React.ReactNode][] = [];
  const skip = new Set(["palette", "scenes", "structure", "document_metadata"]);
  const palette = (data.palette as { hex: string; name?: string; proportion?: number }[] | undefined) ?? (data.colors as { hex: string; proportion?: number }[] | undefined);
  for (const [k, v] of Object.entries(data ?? {})) {
    if (skip.has(k) || v == null || k === "colors") continue;
    if (typeof v === "object" && !Array.isArray(v)) {
      for (const [k2, v2] of Object.entries(v as Json)) {
        if (v2 == null || typeof v2 === "object") continue;
        rows.push([`${humanize(k)} · ${humanize(k2).toLowerCase()}`, String(v2)]);
      }
    } else if (Array.isArray(v)) {
      if (v.length && typeof v[0] !== "object") rows.push([humanize(k), v.join(", ")]);
    } else rows.push([humanize(k), String(v)]);
  }
  const structure = data.structure as Json | undefined;
  if (structure) {
    for (const [k, v] of Object.entries(structure)) if (typeof v !== "object") rows.push([humanize(k), String(v)]);
  }
  return (
    <div className="grid gap-3">
      {palette?.length ? <PaletteBar colors={palette} /> : null}
      {rows.length ? (
        <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-3 gap-y-1 text-sm">
          {rows.slice(0, 24).map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="min-w-0 break-words">{v}</dd>
            </React.Fragment>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

export function PaletteBar({ colors }: { colors: { hex: string; name?: string; proportion?: number }[] }) {
  return (
    <div>
      <div className="flex h-5 overflow-hidden rounded-[3px]" role="img" aria-label={`Measured colors: ${colors.map((c) => c.hex).join(", ")}`}>
        {colors.map((c, i) => (
          <span key={i} title={`${c.hex}${c.name ? " " + c.name : ""}${c.proportion ? ` · ${Math.round(c.proportion * 100)}%` : ""}`} style={{ background: c.hex, flexGrow: c.proportion ?? 1, flexBasis: 0 }} />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
        {colors.slice(0, 6).map((c, i) => (
          <span key={i}>
            {c.hex}
            {c.proportion ? ` ${Math.round(c.proportion * 100)}%` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

/** The AI's reading of the asset: always framed as interpretation (dashed amber rule), never as brand fact. */
export function InterpretationView({ x }: { x: Analysis["interpretive"] }) {
  const concepts = x.aesthetic_concepts ?? [];
  return (
    <div className="ai-block grid gap-3 text-base">
      {x.summary ? <p className="text-md">{x.summary}</p> : null}
      {x.atmosphere?.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Atmosphere</p>
          <Chips items={x.atmosphere} />
        </div>
      ) : null}
      {x.visual_style?.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Visual style</p>
          <Chips items={x.visual_style} />
        </div>
      ) : null}
      {concepts.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Aesthetic concepts recognised</p>
          <ul className="grid gap-1">
            {concepts.map((c) => (
              <li key={c.name} className="grid grid-cols-[1fr_5rem] items-center gap-3 text-sm">
                <span>
                  {c.name}
                  {c.evidence ? <span className="block text-xs text-muted">{c.evidence}</span> : null}
                </span>
                <span className="flex items-center gap-1.5" title={`confidence ${c.confidence ?? "?"}`}>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                    <span className="block h-full bg-ai" style={{ width: `${Math.round((c.confidence ?? 0) * 100)}%` }} />
                  </span>
                  <span className="tabular w-7 text-right text-xs text-muted">{Math.round((c.confidence ?? 0) * 100)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {x.photography_characteristics?.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Photography / camera</p>
          <Chips items={x.photography_characteristics} />
        </div>
      ) : null}
      {x.potential_applications?.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Possible applications</p>
          <Chips items={x.potential_applications} />
        </div>
      ) : null}
      {x.brand_relevance?.assessment && x.brand_relevance.assessment !== "unassessed" ? (
        <p className="text-sm">
          <span className="text-muted">Brand relevance: </span>
          {humanize(x.brand_relevance.assessment)}
          {x.brand_relevance.rationale ? ` — ${x.brand_relevance.rationale}` : ""}
        </p>
      ) : null}
      {x.suggested_tags?.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Suggested tags</p>
          <Chips items={x.suggested_tags} />
        </div>
      ) : null}
    </div>
  );
}

export function AnalysisMeta({ a }: { a: Analysis }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
      <AiTag dev={a.is_development_adapter} label={humanize(a.analysis_type)} />
      <Status status={a.status} />
      <span>
        {a.provider} / <span className="font-mono text-[11px]">{a.model}</span>
      </span>
      {a.prompt_key ? (
        <span>
          prompt <span className="font-mono text-[11px]">{a.prompt_key}</span> v{a.prompt_version}
        </span>
      ) : null}
      <span>schema v{a.schema_version}</span>
      {a.confidence != null ? <span>confidence {Math.round(a.confidence * 100)}%</span> : null}
      {a.processing_ms != null ? <span>{a.processing_ms} ms</span> : null}
      <span>{formatDateTime(a.created_at)}</span>
      {a.validation_errors?.length ? <span className="text-danger">{a.validation_errors.length} validation issue(s)</span> : null}
    </div>
  );
}

export function AnalysisBlock({ a, actions, className }: { a: Analysis; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={cn("grid gap-3 rounded-lg border border-line bg-surface p-4", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <AnalysisMeta a={a} />
        {actions}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1.5 text-sm font-medium">Measured</p>
          <ObjectiveView data={a.objective} />
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Interpretation</p>
          <InterpretationView x={a.interpretive} />
        </div>
      </div>
      {a.review_notes ? <p className="text-sm text-muted">Reviewer note: {a.review_notes}</p> : null}
    </section>
  );
}
