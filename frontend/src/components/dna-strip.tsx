"use client";

import { cn } from "@/lib/utils";
import type { Palette } from "@/lib/types";
import { Tooltip } from "@/components/ui/tooltip";

/**
 * The brand's approved palette as a proportional color barcode — the one visual signature of
 * the platform. Primary colors take more width than accents; approved palettes only.
 */
const ROLE_WEIGHT: Record<string, number> = { primary: 3, neutral: 2, secondary: 2, accent: 1, semantic: 0.6, extended: 0.8 };

export type StripColor = { hex: string; name: string; weight: number };

const ROLE_ORDER = ["primary", "secondary", "neutral", "accent", "semantic", "extended"];

/** Palettes in reading order: primary first, accents and semantic colors after. */
export function sortPalettes<T extends Pick<Palette, "role" | "sort_order">>(palettes: T[]): T[] {
  return [...palettes].sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.sort_order - b.sort_order);
}

export function stripFromPalettes(palettes: Palette[] | undefined, approvedOnly = true): StripColor[] {
  if (!palettes) return [];
  return sortPalettes(palettes)
    .filter((p) => !approvedOnly || p.status === "approved")
    .flatMap((p) => p.colors.map((c) => ({ hex: c.hex, name: c.name, weight: ROLE_WEIGHT[p.role] ?? 1 })));
}

export function DnaStrip({
  colors,
  className,
  height = 8,
  interactive = false,
  label,
}: {
  colors: StripColor[];
  className?: string;
  height?: number;
  interactive?: boolean;
  label?: string;
}) {
  if (!colors.length) {
    return (
      <div
        className={cn("w-full rounded-[2px] border border-dashed border-line-strong", className)}
        style={{ height }}
        aria-label={label ? `${label}: no approved palette yet` : "No approved palette yet"}
        role="img"
      />
    );
  }
  const total = colors.reduce((s, c) => s + c.weight, 0);
  return (
    <div
      role="img"
      aria-label={`${label ? label + " palette: " : "Palette: "}${colors.map((c) => c.name).join(", ")}`}
      className={cn("flex w-full overflow-hidden rounded-[2px]", className)}
      style={{ height }}
    >
      {colors.map((c, i) => {
        const seg = <div key={i} style={{ background: c.hex, flexGrow: c.weight / total, flexBasis: 0 }} className="h-full min-w-[3px]" />;
        return interactive ? (
          <Tooltip key={i} content={`${c.name} ${c.hex.toUpperCase()}`}>
            {seg}
          </Tooltip>
        ) : (
          seg
        );
      })}
    </div>
  );
}
