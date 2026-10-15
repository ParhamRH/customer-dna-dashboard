"use client";
import * as React from "react";
import { Textarea } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { Markdown } from "@/components/markdown";

/** Markdown document editor with a rendered preview (documents are stored as Markdown). */
export function MarkdownEditor({ value, onChange, label = "Document", rows = 10 }: { value: string; onChange: (v: string) => void; label?: string; rows?: number }) {
  const [mode, setMode] = React.useState<"write" | "preview">("write");
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-ink-2">{label}</span>
        <Segmented label={`${label} view`} value={mode} onChange={setMode} options={[{ value: "write", label: "Write" }, { value: "preview", label: "Preview" }]} />
      </div>
      {mode === "write" ? (
        <Textarea aria-label={label} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} className="font-serif text-md leading-relaxed" placeholder="Markdown supported: ## headings, **bold**, lists, links, tables." />
      ) : (
        <div className="min-h-32 rounded-md border border-line bg-surface p-4">{value.trim() ? <Markdown>{value}</Markdown> : <p className="text-muted">Nothing written yet.</p>}</div>
      )}
    </div>
  );
}
