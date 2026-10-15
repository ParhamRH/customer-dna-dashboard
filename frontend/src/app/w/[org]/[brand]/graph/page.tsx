"use client";
import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { ArrowUpRight, Maximize2, Minus, Plus, X } from "lucide-react";
import { useWorkspace } from "@/lib/workspace";
import { useOnChange, useResetState } from "@/lib/state";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { ENTITY_LABELS, RELATION_LABELS } from "@/lib/labels";
import { cn, humanize, pluralize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Segmented } from "@/components/ui/tabs";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Status, Tag } from "@/components/status";
import { entityHref } from "@/components/knowledge/item-tabs";

type N = GraphNode & SimulationNodeDatum & { degree: number };
type L = SimulationLinkDatum<N> & GraphEdge & { s: string; t: string };
type View = "map" | "list";

const TYPE_ORDER = ["aesthetic_concept", "principle", "guideline", "asset", "project", "collection", "knowledge_entry"];
const NEGATIVE = new Set(["violates", "opposes"]);
const ASSET = 30;

function radius(n: N) {
  if (n.type === "asset") return ASSET / 2 + 2;
  if (n.type === "aesthetic_concept") return 7 + Math.min(n.degree, 8);
  return 8;
}
/** Projects and collections have no approval workflow, so they are always drawn filled. */
const approved = (n: N) => n.type === "project" || n.type === "collection" || n.status === "approved" || n.status === "official";

/** Each entity type has its own shape so the map reads without color. Filled = approved. */
function Shape({ type, filled, r, className }: { type: string; filled: boolean; r: number; className?: string }) {
  const fill = filled ? "currentColor" : "var(--surface)";
  const common = { fill, stroke: "currentColor", strokeWidth: 1.5, className };
  switch (type) {
    case "aesthetic_concept":
      return <circle r={r} {...common} />;
    case "principle":
      return <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} transform="rotate(45)" {...common} />;
    case "guideline":
      return <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} rx={1.5} {...common} />;
    case "project": {
      const pts = Array.from({ length: 6 }, (_, i) => {
        const a = (Math.PI / 3) * i + Math.PI / 6;
        return `${(Math.cos(a) * r).toFixed(2)},${(Math.sin(a) * r).toFixed(2)}`;
      }).join(" ");
      return <polygon points={pts} {...common} />;
    }
    case "knowledge_entry":
      return <polygon points={`0,${-r} ${r * 0.9},${r * 0.7} ${-r * 0.9},${r * 0.7}`} {...common} />;
    case "collection":
      return (
        <g className={className}>
          <rect x={-r + 3} y={-r - 1} width={r * 1.6} height={r * 1.6} rx={1.5} fill="var(--surface)" stroke="currentColor" strokeWidth={1.2} />
          <rect x={-r} y={-r + 2} width={r * 1.6} height={r * 1.6} rx={1.5} fill={fill} stroke="currentColor" strokeWidth={1.5} />
        </g>
      );
    default:
      return <circle r={r * 0.7} {...common} />;
  }
}

const TONE: Record<string, string> = {
  aesthetic_concept: "text-accent",
  principle: "text-ink",
  guideline: "text-ink-2",
  project: "text-ink-2",
  collection: "text-ink-2",
  knowledge_entry: "text-muted",
};

function Legend({ types }: { types: string[] }) {
  return (
    <div className="grid gap-3 text-sm">
      <ul className="grid gap-1.5">
        {types.map((t) => (
          <li key={t} className="flex items-center gap-2">
            <svg width="20" height="20" viewBox="-10 -10 20 20" aria-hidden className={TONE[t] ?? "text-ink-2"}>
              {t === "asset" ? <rect x={-8} y={-8} width={16} height={16} rx={3} fill="var(--sunken)" stroke="var(--line-strong)" /> : <Shape type={t} filled r={7} />}
            </svg>
            {ENTITY_LABELS[t] ?? humanize(t)}
          </li>
        ))}
      </ul>
      <ul className="grid gap-1.5 text-muted">
        <li className="flex items-center gap-2">
          <svg width="20" height="8" aria-hidden>
            <line x1="0" y1="4" x2="20" y2="4" stroke="var(--line-strong)" strokeWidth="1.5" />
          </svg>
          Approved relationship
        </li>
        <li className="flex items-center gap-2">
          <svg width="20" height="8" aria-hidden>
            <line x1="0" y1="4" x2="20" y2="4" stroke="var(--danger)" strokeWidth="1.5" strokeOpacity=".7" />
          </svg>
          Violates / opposes
        </li>
        <li className="flex items-center gap-2">
          <svg width="20" height="8" aria-hidden>
            <line x1="0" y1="4" x2="20" y2="4" stroke="var(--ai-line)" strokeWidth="1.5" strokeDasharray="4 3" />
          </svg>
          AI suggestion, not reviewed
        </li>
        <li className="flex items-center gap-2">
          <svg width="20" height="20" viewBox="-10 -10 20 20" aria-hidden className="text-accent">
            <circle r={6} fill="var(--surface)" stroke="currentColor" strokeWidth={1.5} />
          </svg>
          Hollow = not approved yet
        </li>
      </ul>
    </div>
  );
}

function useSize(ref: React.RefObject<HTMLElement | null>) {
  const [s, setS] = React.useState({ w: 800, h: 560 });
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setS({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return s;
}

function GraphMap({
  nodes,
  links,
  selected,
  onSelect,
  focusKey,
}: {
  nodes: N[];
  links: L[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  focusKey: number;
}) {
  const wrap = React.useRef<HTMLDivElement>(null);
  const svg = React.useRef<SVGSVGElement>(null);
  const size = useSize(wrap);
  const [, setFrame] = React.useState(0);
  const [hover, setHover] = React.useState<string | null>(null);
  const drag = React.useRef<{ kind: "node"; node: N; moved: boolean } | { kind: "pan"; x: number; y: number; tx: number; ty: number } | null>(null);

  // The layout is a pure function of the data: settle the simulation synchronously, then keep it
  // around so dragging a node can reheat it.
  const sim = React.useMemo<Simulation<N, L>>(() => {
    const s = forceSimulation<N, L>(nodes)
      .force(
        "link",
        forceLink<N, L>(links)
          .id((d) => d.id)
          .distance((l) => (l.relation_type === "exemplifies" ? 70 : 110))
          .strength(0.45),
      )
      .force("charge", forceManyBody<N>().strength((d) => (d.type === "asset" ? -140 : -320)))
      // leave room for the label under non-asset nodes
      .force("collide", forceCollide<N>((d) => (d.type === "asset" ? radius(d) + 6 : Math.max(radius(d) + 10, Math.min(d.label.length * 3.1, 64)))))
      .force("x", forceX<N>(0).strength(0.06))
      .force("y", forceY<N>(0).strength(0.06))
      .stop();
    for (let i = 0; i < 320; i++) s.tick();
    return s;
  }, [nodes, links]);
  React.useEffect(() => {
    sim.on("tick", () => setFrame((f) => f + 1));
    return () => {
      sim.on("tick", null);
      sim.stop();
    };
  }, [sim]);

  const fitted = () => {
    if (!nodes.length) return { x: 0, y: 0, k: 1 };
    const xs = nodes.map((n) => n.x ?? 0);
    const ys = nodes.map((n) => n.y ?? 0);
    const [x0, x1, y0, y1] = [Math.min(...xs) - 60, Math.max(...xs) + 60, Math.min(...ys) - 50, Math.max(...ys) + 50];
    const k = Math.min(1.6, Math.min(size.w / (x1 - x0), size.h / (y1 - y0)));
    return { k, x: size.w / 2 - ((x0 + x1) / 2) * k, y: size.h / 2 - ((y0 + y1) / 2) * k };
  };
  // Refit whenever the layout or the container size changes.
  const [tf, setTf] = useResetState([sim, size.w, size.h], fitted);
  const fit = () => setTf(fitted());

  // Center on the selected node when a search or ?focus= asks for it.
  useOnChange(focusKey, () => {
    const n = selected ? nodes.find((x) => x.id === selected) : undefined;
    if (focusKey && n) setTf((t) => ({ ...t, x: size.w / 2 - (n.x ?? 0) * t.k, y: size.h / 2 - (n.y ?? 0) * t.k }));
  });

  React.useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      setTf((t) => {
        const k = Math.max(0.2, Math.min(4, t.k * Math.exp(-e.deltaY * 0.0015)));
        return { k, x: px - ((px - t.x) * k) / t.k, y: py - ((py - t.y) * k) / t.k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [setTf]);

  const toGraph = (e: React.PointerEvent) => {
    const r = svg.current!.getBoundingClientRect();
    return { x: (e.clientX - r.left - tf.x) / tf.k, y: (e.clientY - r.top - tf.y) / tf.k };
  };
  const zoom = (f: number) =>
    setTf((t) => {
      const k = Math.max(0.2, Math.min(4, t.k * f));
      return { k, x: size.w / 2 - ((size.w / 2 - t.x) * k) / t.k, y: size.h / 2 - ((size.h / 2 - t.y) * k) / t.k };
    });

  const focus = hover ?? selected;
  const near = React.useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    for (const l of links) {
      const a = (l.source as N).id;
      const b = (l.target as N).id;
      if (a === focus) s.add(b);
      if (b === focus) s.add(a);
    }
    return s;
  }, [focus, links]);

  return (
    <div ref={wrap} className="relative h-[calc(100dvh-15rem)] min-h-[520px] overflow-hidden rounded-lg border border-line bg-surface">
      <svg
        ref={svg}
        width={size.w}
        height={size.h}
        className="block cursor-grab touch-none select-none active:cursor-grabbing"
        role="img"
        aria-label={`Knowledge graph with ${pluralize(nodes.length, "node")} and ${pluralize(links.length, "relationship")}. Use the list view for a readable table.`}
        onPointerDown={(e) => {
          if (e.target === svg.current) {
            drag.current = { kind: "pan", x: e.clientX, y: e.clientY, tx: tf.x, ty: tf.y };
            (e.target as Element).setPointerCapture(e.pointerId);
          }
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          if (d.kind === "pan") setTf((t) => ({ ...t, x: d.tx + e.clientX - d.x, y: d.ty + e.clientY - d.y }));
          else {
            const p = toGraph(e);
            d.node.fx = p.x;
            d.node.fy = p.y;
            d.moved = true;
            sim.alphaTarget(0.25).restart();
          }
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (!d) return;
          if (d.kind === "pan") {
            if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) < 4) onSelect(null);
          } else {
            sim.alphaTarget(0);
            d.node.fx = null;
            d.node.fy = null;
            if (!d.moved) onSelect(d.node.id === selected ? null : d.node.id);
          }
        }}
      >
        <defs>
          <clipPath id="asset-clip">
            <rect x={-ASSET / 2} y={-ASSET / 2} width={ASSET} height={ASSET} rx={4} />
          </clipPath>
        </defs>
        <g transform={`translate(${tf.x},${tf.y}) scale(${tf.k})`}>
          <g>
            {links.map((l) => {
              const a = l.source as N;
              const b = l.target as N;
              const on = !near || (near.has(a.id) && near.has(b.id) && (a.id === focus || b.id === focus));
              const suggested = l.status === "suggested";
              return (
                <line
                  key={l.id}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={suggested ? "var(--ai-line)" : NEGATIVE.has(l.relation_type) ? "var(--danger)" : near && on ? "var(--ink-2)" : "var(--line-strong)"}
                  strokeOpacity={on ? (NEGATIVE.has(l.relation_type) ? 0.7 : 1) : 0.15}
                  strokeWidth={(near && on ? 1.6 : 1.1) / Math.sqrt(tf.k)}
                  strokeDasharray={suggested ? "4 3" : undefined}
                />
              );
            })}
          </g>
          {near && focus
            ? links
                .filter((l) => (l.source as N).id === focus || (l.target as N).id === focus)
                .map((l) => {
                  const a = l.source as N;
                  const b = l.target as N;
                  return (
                    <text key={`t-${l.id}`} x={((a.x ?? 0) + (b.x ?? 0)) / 2} y={((a.y ?? 0) + (b.y ?? 0)) / 2} textAnchor="middle" dy="0.32em" className="pointer-events-none fill-muted" style={{ fontSize: 10 / tf.k, paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: 3 / tf.k }}>
                      {RELATION_LABELS[l.relation_type] ?? l.relation_type}
                    </text>
                  );
                })
            : null}
          {nodes.map((n) => {
            const dim = near && !near.has(n.id);
            const isSel = n.id === selected;
            const r = radius(n);
            return (
              <g
                key={n.id}
                transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                opacity={dim ? 0.22 : 1}
                className="cursor-pointer outline-none"
                tabIndex={nodes.length <= 200 ? 0 : -1}
                role="button"
                aria-label={`${ENTITY_LABELS[n.type] ?? n.type}: ${n.label}`}
                aria-pressed={isSel}
                onPointerEnter={() => setHover(n.id)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(n.id)}
                onBlur={() => setHover(null)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(isSel ? null : n.id);
                  }
                }}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  drag.current = { kind: "node", node: n, moved: false };
                  svg.current?.setPointerCapture(e.pointerId);
                }}
              >
                {n.type === "asset" ? (
                  <>
                    {n.thumbnail_url ? (
                      <image href={n.thumbnail_url} x={-ASSET / 2} y={-ASSET / 2} width={ASSET} height={ASSET} preserveAspectRatio="xMidYMid slice" clipPath="url(#asset-clip)" />
                    ) : (
                      <rect x={-ASSET / 2} y={-ASSET / 2} width={ASSET} height={ASSET} rx={4} fill="var(--sunken)" />
                    )}
                    <rect
                      x={-ASSET / 2}
                      y={-ASSET / 2}
                      width={ASSET}
                      height={ASSET}
                      rx={4}
                      fill="none"
                      stroke={isSel ? "var(--accent)" : "var(--line-strong)"}
                      strokeWidth={isSel ? 2.5 : 1}
                      strokeDasharray={n.reference_role === "inspiration" || n.reference_role === "external" ? "3 2" : undefined}
                    />
                  </>
                ) : (
                  <>
                    {isSel ? <circle r={r + 5} fill="none" stroke="var(--accent)" strokeWidth={2} /> : null}
                    <Shape type={n.type} filled={approved(n)} r={r} className={TONE[n.type] ?? "text-ink-2"} />
                  </>
                )}
              </g>
            );
          })}
          <g className="pointer-events-none" aria-hidden>
            {nodes.map((n) => {
              if (n.type === "asset" && n.id !== focus) return null;
              const dim = near && !near.has(n.id);
              const isSel = n.id === selected;
              return (
                <text
                  key={`l-${n.id}`}
                  x={n.x ?? 0}
                  y={(n.y ?? 0) + radius(n) + 13 / tf.k}
                  opacity={dim ? 0.25 : 1}
                  textAnchor="middle"
                  className={cn("fill-ink-2", (n.type === "aesthetic_concept" || isSel) && "fill-ink font-medium")}
                  style={{ fontSize: 11 / tf.k, paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: 3.5 / tf.k, strokeLinejoin: "round" }}
                >
                  {n.label.length > 34 ? n.label.slice(0, 32) + "…" : n.label}
                </text>
              );
            })}
          </g>
        </g>
      </svg>
      <div className="absolute bottom-3 right-3 flex flex-col overflow-hidden rounded-md border border-line bg-surface shadow-pop">
        <Button variant="ghost" size="icon-sm" className="rounded-none" aria-label="Zoom in" onClick={() => zoom(1.25)}>
          <Plus />
        </Button>
        <Button variant="ghost" size="icon-sm" className="rounded-none" aria-label="Zoom out" onClick={() => zoom(0.8)}>
          <Minus />
        </Button>
        <Button variant="ghost" size="icon-sm" className="rounded-none" aria-label="Fit graph to view" onClick={fit}>
          <Maximize2 />
        </Button>
      </div>
      <p className="pointer-events-none absolute bottom-3 left-3 text-xs text-faint">Drag to pan · scroll to zoom · drag a node to move it</p>
    </div>
  );
}

function Details({ node, links, byId, onSelect }: { node: N; links: L[]; byId: Map<string, N>; onSelect: (id: string) => void }) {
  const ws = useWorkspace();
  const mine = links.filter((l) => l.s === node.id || l.t === node.id);
  return (
    <div className="grid gap-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-muted">{node.type === "asset" ? humanize(node.asset_type ?? "asset") : ENTITY_LABELS[node.type] ?? humanize(node.type)}</p>
          <h2 className="text-lg font-semibold leading-snug">{node.label}</h2>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Clear selection" onClick={() => onSelect("")}>
          <X />
        </Button>
      </div>
      {node.thumbnail_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={node.thumbnail_url} alt="" className="aspect-[4/3] w-full rounded-md bg-sunken object-cover" />
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Status status={node.status} />
        {node.reference_role && node.reference_role !== "brand_asset" ? <Tag tone="outline">{humanize(node.reference_role)}</Tag> : null}
      </div>
      <Button asChild size="sm" className="justify-self-start">
        <Link href={entityHref(ws.base, node.type, node.entity_id)}>
          Open <ArrowUpRight />
        </Link>
      </Button>
      <div>
        <h3 className="mb-1.5 text-sm font-medium">{pluralize(mine.length, "relationship")}</h3>
        <ul className="grid gap-1">
          {mine.map((l) => {
            const out = l.s === node.id;
            const other = byId.get(out ? l.t : l.s);
            if (!other) return null;
            return (
              <li key={l.id} className="text-sm">
                <span className="text-muted">{out ? (RELATION_LABELS[l.relation_type] ?? l.relation_type) : `← ${RELATION_LABELS[l.relation_type] ?? l.relation_type}`}</span>{" "}
                <button className="text-left font-medium hover:underline" onClick={() => onSelect(other.id)}>
                  {other.label}
                </button>
                {l.status === "suggested" ? <span className="ml-1.5 text-xs text-ai">AI suggestion</span> : null}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export default function GraphPage() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const [view, setView] = React.useState<View>("map");
  const [suggested, setSuggested] = React.useState(false);
  const [hidden, setHidden] = React.useState<string[]>([]);
  const [isolated, setIsolated] = React.useState(false);
  const [selected, setSelected] = React.useState<string | null>(params.get("focus"));
  const [focusKey, setFocusKey] = React.useState(params.get("focus") ? 1 : 0);
  const [q, setQ] = React.useState("");
  const g = useQuery({
    queryKey: ws.key("graph", ws.brand.id, suggested),
    queryFn: () => ws.req<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/v1/brands/${ws.brand.id}/graph`, { params: { include_suggested: suggested } }),
  });

  const types = React.useMemo(() => {
    const present = new Set((g.data?.nodes ?? []).map((n) => n.type));
    return [...TYPE_ORDER.filter((t) => present.has(t)), ...[...present].filter((t) => !TYPE_ORDER.includes(t))];
  }, [g.data]);

  const { nodes, links, byId, alone } = React.useMemo(() => {
    const ns: N[] = (g.data?.nodes ?? []).filter((n) => !hidden.includes(n.type)).map((n) => ({ ...n, degree: 0 }));
    const m = new Map(ns.map((n) => [n.id, n]));
    const ls: L[] = (g.data?.edges ?? [])
      .filter((e) => m.has(e.source) && m.has(e.target))
      .map((e) => ({ ...e, s: e.source, t: e.target, source: e.source, target: e.target }));
    for (const l of ls) {
      m.get(l.s)!.degree++;
      m.get(l.t)!.degree++;
    }
    const alone = ns.filter((n) => n.degree === 0);
    const shown = isolated ? ns : ns.filter((n) => n.degree > 0);
    return { nodes: shown, links: ls, byId: m, alone };
  }, [g.data, hidden, isolated]);

  const select = (id: string | null) => setSelected(id || null);
  const find = () => {
    const t = q.trim().toLowerCase();
    if (!t) return;
    const n = nodes.find((x) => x.label?.toLowerCase().includes(t));
    if (n) {
      setSelected(n.id);
      setFocusKey((k) => k + 1);
    }
  };
  const node = selected ? byId.get(selected) : undefined;

  return (
    <Main wide>
      <PageHeader
        title="Knowledge graph"
        description="How concepts, principles, assets and projects relate. Only reviewed relationships are shown unless you choose to see AI suggestions."
      />
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Segmented<View>
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: "map", label: "Map" },
            { value: "list", label: "List" },
          ]}
        />
        <div className="flex flex-wrap gap-1" role="group" aria-label="Show entity types">
          {types.map((t) => {
            const on = !hidden.includes(t);
            return (
              <button
                key={t}
                aria-pressed={on}
                onClick={() => setHidden(on ? [...hidden, t] : hidden.filter((x) => x !== t))}
                className={cn("h-6 rounded-full border px-2.5 text-sm", on ? "border-ink bg-ink text-paper" : "border-line-strong text-muted hover:text-ink")}
              >
                {ENTITY_LABELS[t] ?? humanize(t)}
              </button>
            );
          })}
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <Switch checked={suggested} onCheckedChange={setSuggested} /> Show AI suggestions
        </label>
        <form
          className="ml-auto flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            find();
          }}
        >
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a node" aria-label="Find a node" className="h-8 w-48" />
          <Button size="sm" type="submit" disabled={!q.trim()}>
            Find
          </Button>
        </form>
      </div>
      {g.error ? <ErrorState error={g.error} /> : null}
      {!g.data ? (
        <LoadingBlock rows={6} />
      ) : g.data.nodes.length === 0 ? (
        <EmptyState title="No relationships yet">Link assets to concepts and principles — or accept AI relationship suggestions in the review queue — and the graph builds itself.</EmptyState>
      ) : view === "map" ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <GraphMap nodes={nodes} links={links} selected={selected} onSelect={select} focusKey={focusKey} />
          <aside className="lg:max-h-[calc(100dvh-15rem)] lg:overflow-y-auto">
            {node ? (
              <Details node={node} links={links} byId={byId} onSelect={(id) => select(id)} />
            ) : (
              <div className="grid gap-5">
                <p className="text-sm text-muted">
                  {pluralize(nodes.length, "node")} · {pluralize(links.length, "relationship")}. Select a node to see what it connects to.
                </p>
                <Legend types={types} />
                {alone.length ? (
                  <div className="border-t border-line pt-4">
                    <h3 className="text-sm font-medium">Not connected yet</h3>
                    <p className="mt-0.5 text-sm text-muted">
                      {alone.length} {alone.length === 1 ? "item has" : "items have"} no relationships. Link them to example assets or projects to bring them into the graph.
                    </p>
                    <ul className="mt-2 grid gap-1">
                      {alone.slice(0, 12).map((n) => (
                        <li key={n.id} className="text-sm">
                          <Link href={entityHref(ws.base, n.type, n.entity_id)} className="hover:underline">
                            {n.label}
                          </Link>{" "}
                          <span className="text-xs text-muted">{ENTITY_LABELS[n.type]}</span>
                        </li>
                      ))}
                    </ul>
                    <label className="mt-3 flex items-center gap-2 text-sm text-ink-2">
                      <Switch checked={isolated} onCheckedChange={setIsolated} /> Show them on the map
                    </label>
                  </div>
                ) : null}
              </div>
            )}
          </aside>
        </div>
      ) : (
        <Table>
          <THead>
            <tr>
              <th>From</th>
              <th>Relationship</th>
              <th>To</th>
              <th>Status</th>
            </tr>
          </THead>
          <TBody>
            {[...links]
              .sort((a, b) => a.relation_type.localeCompare(b.relation_type) || (byId.get(a.s)?.label ?? "").localeCompare(byId.get(b.s)?.label ?? ""))
              .map((l) => {
                const a = byId.get(l.s)!;
                const b = byId.get(l.t)!;
                return (
                  <tr key={l.id}>
                    <td>
                      <Link href={entityHref(ws.base, a.type, a.entity_id)} className="font-medium hover:underline">
                        {a.label}
                      </Link>
                      <div className="text-xs text-muted">{ENTITY_LABELS[a.type]}</div>
                    </td>
                    <td className="text-sm">{RELATION_LABELS[l.relation_type] ?? l.relation_type}</td>
                    <td>
                      <Link href={entityHref(ws.base, b.type, b.entity_id)} className="font-medium hover:underline">
                        {b.label}
                      </Link>
                      <div className="text-xs text-muted">{ENTITY_LABELS[b.type]}</div>
                    </td>
                    <td>{l.status === "suggested" ? <span className="text-sm text-ai">AI suggestion</span> : <Status status={l.status} label="Approved" />}</td>
                  </tr>
                );
              })}
          </TBody>
        </Table>
      )}
    </Main>
  );
}
