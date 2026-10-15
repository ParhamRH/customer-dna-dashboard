"use client";
import * as React from "react";
import { Plus, X } from "lucide-react";
import type { FieldSpec, Json } from "@/lib/types";
import { cn, humanize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/* Art-direction entries separate measurable observations from aesthetic interpretation. */
const OBSERVED = new Set(["objective_observations"]);
const INTERPRETED = new Set(["aesthetic_interpretation"]);

function isEmpty(v: unknown) {
  return v == null || v === "" || (Array.isArray(v) && v.length === 0) || (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0);
}

/** Read-only rendering of an entry's structured fields, following the registry field specs. */
export function StructuredView({ fields, data, official }: { fields: FieldSpec[]; data: Json; official?: boolean }) {
  const shown = fields.filter((f) => !isEmpty(data?.[f.key]));
  const unknown = Object.keys(data ?? {}).filter((k) => !fields.some((f) => f.key === k) && !isEmpty(data[k]));
  if (!shown.length && !unknown.length) return null;
  return (
    <div className="grid gap-4">
      {shown.map((f) => {
        const v = data[f.key];
        return (
          <div key={f.key} className={cn(INTERPRETED.has(f.key) && "border-l-2 border-line-strong pl-3")}>
            <p className="mb-1 text-sm text-muted">
              {f.label}
              {OBSERVED.has(f.key) ? <span className="ml-1.5 text-xs">— measurable, objective</span> : null}
              {INTERPRETED.has(f.key) ? <span className="ml-1.5 text-xs">— subjective reading</span> : null}
            </p>
            {f.kind === "text" ? (
              <p className={cn(official ? "official-text" : "text-md", INTERPRETED.has(f.key) && "italic")}>{String(v)}</p>
            ) : f.kind === "list" ? (
              <ul className="grid gap-1">
                {(v as string[]).map((x, i) => (
                  <li key={i} className="flex gap-2 text-md">
                    <span className={cn("mt-2.5 size-1 shrink-0 rounded-full", f.key === "dont" ? "bg-danger" : f.key === "do" ? "bg-accent" : "bg-ink-2")} aria-hidden />
                    <span>{x}</span>
                  </li>
                ))}
              </ul>
            ) : f.kind === "records" ? (
              <div className="overflow-x-auto">
                <table className="w-full text-base">
                  <thead>
                    <tr className="text-left text-sm text-muted">
                      {(f.fields ?? []).map((c) => (
                        <th key={c} className="border-b border-line py-1 pr-4 font-medium">
                          {humanize(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(v as Json[]).map((row, i) => (
                      <tr key={i} className="align-top">
                        {(f.fields ?? []).map((c) => (
                          <td key={c} className={cn("border-b border-line py-1.5 pr-4", c === (f.fields ?? [])[0] && "font-medium")}>
                            {String(row?.[c] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <dl className="grid grid-cols-[minmax(6rem,auto)_1fr] gap-x-4 gap-y-1 text-base">
                {Object.entries(v as Json).map(([k, val]) => (
                  <React.Fragment key={k}>
                    <dt className="font-mono text-[12px] text-muted">{k}</dt>
                    <dd>{typeof val === "object" ? JSON.stringify(val) : String(val)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
          </div>
        );
      })}
      {unknown.map((k) => (
        <div key={k}>
          <p className="mb-1 text-sm text-muted">{humanize(k)}</p>
          <pre className="font-mono text-[12px] text-ink-2">{JSON.stringify(data[k], null, 2)}</pre>
        </div>
      ))}
    </div>
  );
}

/** Editor for a list of strings: one input per item, add/remove. */
export function ListEditor({ value, onChange, label, placeholder }: { value: string[]; onChange: (v: string[]) => void; label: string; placeholder?: string }) {
  const items = value.length ? value : [""];
  return (
    <div className="grid gap-1.5" role="group" aria-label={label}>
      {items.map((v, i) => (
        <div key={i} className="flex gap-1.5">
          <Input
            aria-label={`${label} ${i + 1}`}
            value={v}
            placeholder={placeholder}
            onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onChange([...items.slice(0, i + 1), "", ...items.slice(i + 1)]);
              }
            }}
          />
          <Button size="icon" variant="ghost" aria-label="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>
            <X />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="ghost" className="justify-self-start" onClick={() => onChange([...items, ""])}>
        <Plus /> Add
      </Button>
    </div>
  );
}

function RecordsEditor({ value, onChange, columns, label }: { value: Json[]; onChange: (v: Json[]) => void; columns: string[]; label: string }) {
  return (
    <div className="grid gap-2" role="group" aria-label={label}>
      {value.map((row, i) => (
        <div key={i} className="grid gap-1.5 rounded-md border border-line p-2" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0,1fr)) auto` }}>
          {columns.map((c) => (
            <Input
              key={c}
              aria-label={`${humanize(c)} ${i + 1}`}
              placeholder={humanize(c)}
              value={String(row?.[c] ?? "")}
              onChange={(e) => onChange(value.map((r, j) => (j === i ? { ...r, [c]: e.target.value } : r)))}
            />
          ))}
          <Button size="icon" variant="ghost" aria-label="Remove row" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <X />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="ghost" className="justify-self-start" onClick={() => onChange([...value, Object.fromEntries(columns.map((c) => [c, ""]))])}>
        <Plus /> Add row
      </Button>
    </div>
  );
}

function ObjectEditor({ value, onChange, label }: { value: Json; onChange: (v: Json) => void; label: string }) {
  const [text, setText] = React.useState(() => JSON.stringify(value ?? {}, null, 2));
  const [err, setErr] = React.useState<string | null>(null);
  return (
    <div className="grid gap-1">
      <Textarea
        aria-label={label}
        className="font-mono text-[12.5px]"
        rows={5}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value || "{}");
            if (typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Must be an object");
            setErr(null);
            onChange(parsed);
          } catch (x) {
            setErr(x instanceof Error ? x.message : "Invalid JSON");
          }
        }}
      />
      <p className={cn("text-sm", err ? "text-danger" : "text-muted")}>{err ?? 'Key/value pairs as JSON, e.g. {"gutter": "24px"}'}</p>
    </div>
  );
}

/** Structured metadata form generated from the registry's field specs (no schema change per field). */
export function StructuredForm({ fields, value, onChange }: { fields: FieldSpec[]; value: Json; onChange: (v: Json) => void }) {
  if (!fields.length) return <p className="text-sm text-muted">This entry type has no structured fields; use the document text.</p>;
  const set = (k: string, v: unknown) => {
    const next = { ...value };
    if (isEmpty(v) || (Array.isArray(v) && v.every((x) => x === ""))) delete next[k];
    else next[k] = Array.isArray(v) && v.every((x) => typeof x === "string") ? (v as string[]).filter((x) => x.trim()) : v;
    onChange(next);
  };
  return (
    <div className="grid gap-4">
      {fields.map((f) => (
        <div key={f.key} className="grid gap-1.5">
          <Label>
            {f.label}
            {OBSERVED.has(f.key) ? <span className="ml-1 font-normal text-muted">— what can be seen or measured</span> : null}
            {INTERPRETED.has(f.key) ? <span className="ml-1 font-normal text-muted">— the aesthetic reading</span> : null}
          </Label>
          {f.kind === "text" ? (
            <Textarea aria-label={f.label} rows={2} value={String(value?.[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
          ) : f.kind === "list" ? (
            <ListEditor label={f.label} value={(value?.[f.key] as string[]) ?? []} onChange={(v) => set(f.key, v)} />
          ) : f.kind === "records" ? (
            <RecordsEditor label={f.label} columns={f.fields ?? ["value"]} value={(value?.[f.key] as Json[]) ?? []} onChange={(v) => set(f.key, v)} />
          ) : (
            <ObjectEditor label={f.label} value={(value?.[f.key] as Json) ?? {}} onChange={(v) => set(f.key, v)} />
          )}
        </div>
      ))}
    </div>
  );
}
