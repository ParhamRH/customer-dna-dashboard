"use client";
import * as React from "react";
import { Check, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { cn, copyText, downloadText } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function CodeBlock({
  code,
  filename,
  mime = "text/plain",
  className,
  maxHeight = "28rem",
  label,
}: {
  code: string;
  filename?: string;
  mime?: string;
  className?: string;
  maxHeight?: string;
  label?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  return (
    <div className={cn("overflow-hidden rounded-md border border-line bg-surface-2", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-1.5">
        <span className="text-sm text-muted">{label ?? filename ?? "Preview"}</span>
        <div className="flex gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={async () => {
              if (await copyText(code)) {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              } else toast.error("Clipboard is not available in this browser");
            }}
          >
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
          </Button>
          {filename ? (
            <Button size="sm" variant="ghost" onClick={() => downloadText(filename, code, mime)}>
              <Download /> Download
            </Button>
          ) : null}
        </div>
      </div>
      <pre className="overflow-auto p-3 font-mono text-[12.5px] leading-relaxed text-ink" style={{ maxHeight }}>
        {code}
      </pre>
    </div>
  );
}

/** Monospace value with click-to-copy (hex codes, token paths, checksums, IDs). */
export function CopyValue({ value, display, className }: { value: string; display?: string; className?: string }) {
  return (
    <button
      type="button"
      title="Copy"
      onClick={async () => {
        if (await copyText(value)) toast.success("Copied to clipboard");
      }}
      className={cn("rounded-sm font-mono text-[12px] text-ink-2 hover:bg-sunken hover:text-ink", className)}
    >
      {display ?? value}
    </button>
  );
}
