"use client";
import * as React from "react";
import { cn, formatNumber } from "@/lib/utils";

/**
 * Small, dependency-free charts that follow one spec: a single series in one hue (the
 * accent), columns ≤ 24px with a 4px rounded data-end, hairline recessive gridlines,
 * hover tooltips, and an equivalent data table for screen readers.
 */

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * p;
}

function compact(n: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function ColumnChart({
  data,
  height = 140,
  className,
  title,
  valueLabel = "value",
}: {
  data: { label: string; value: number; tooltip?: string }[];
  height?: number;
  className?: string;
  title: string;
  valueLabel?: string;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(600);
  React.useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
  const padL = 32;
  const padB = 20;
  const plotW = Math.max(10, width - padL);
  const plotH = height - padB;
  const band = plotW / Math.max(1, data.length);
  const barW = Math.min(24, Math.max(4, band - 2));
  const ticks = [0, max / 2, max];
  const y = (v: number) => plotH - (v / max) * plotH;
  const labelEvery = Math.ceil(data.length / Math.max(1, Math.floor(plotW / 56)));
  return (
    <figure className={cn("relative", className)} aria-label={title}>
      <div ref={ref} className="w-full">
        <svg width={width} height={height} role="img" aria-hidden className="block overflow-visible">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={padL} x2={width} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
              <text x={padL - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted text-[10px] tabular">
                {compact(t)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = padL + i * band + (band - barW) / 2;
            const h = Math.max(d.value > 0 ? 2 : 0, plotH - y(d.value));
            const r = Math.min(4, h, barW / 2);
            const top = plotH - h;
            const path = `M${x},${plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${plotH} Z`;
            return (
              <g key={d.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <rect x={padL + i * band} y={0} width={band} height={plotH} fill="transparent" />
                {h > 0 ? <path d={path} fill="var(--accent)" opacity={hover === null || hover === i ? 1 : 0.45} /> : null}
                {i % labelEvery === 0 ? (
                  <text x={x + barW / 2} y={height - 4} textAnchor="middle" className="fill-muted text-[10px]">
                    {d.label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
      {hover !== null && data[hover] ? (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-line bg-surface px-2 py-1 text-sm shadow-pop"
          style={{ left: padL + hover * band + band / 2, top: y(data[hover].value) - 6 }}
        >
          <div className="text-muted">{data[hover].tooltip ?? data[hover].label}</div>
          <div className="font-medium text-ink">
            {formatNumber(data[hover].value)} {valueLabel}
          </div>
        </div>
      ) : null}
      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <th>{d.tooltip ?? d.label}</th>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Horizontal magnitude bars with the value at the tip. One hue; text stays in ink tokens. */
export function BarList({
  items,
  className,
  format = formatNumber,
  tone = "accent",
}: {
  items: { label: React.ReactNode; value: number; key?: string; secondary?: React.ReactNode }[];
  className?: string;
  format?: (n: number) => string;
  tone?: "accent" | "ink" | "ai";
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  const fill = { accent: "bg-accent", ink: "bg-ink-2", ai: "bg-ai" }[tone];
  return (
    <ul className={cn("grid gap-2.5", className)}>
      {items.map((it, idx) => (
        <li key={it.key ?? idx} className="grid grid-cols-[minmax(7rem,11rem)_1fr] items-center gap-3 text-base">
          <span className="truncate text-ink-2">{it.label}</span>
          <span className="flex items-center gap-2">
            <span className={cn("h-2.5 rounded-r-[4px]", fill)} style={{ width: `${Math.max(1.5, (it.value / max) * 100)}%`, maxWidth: "calc(100% - 4rem)" }} />
            <span className="tabular text-sm text-ink">{format(it.value)}</span>
            {it.secondary ? <span className="text-sm text-muted">{it.secondary}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
