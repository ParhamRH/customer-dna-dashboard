"use client";
import * as React from "react";
import { Box, FileText, Film, Globe, ImageIcon, Music, Presentation, Shapes, Type } from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import type { AssetSummary } from "@/lib/types";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  video: Film,
  animation: Film,
  model_3d: Box,
  render_3d: Box,
  document: FileText,
  presentation: Presentation,
  text: Type,
  external_reference: Globe,
  audio: Music,
  logo: Shapes,
};

export function AssetTypeIcon({ type, className }: { type: string; className?: string }) {
  const Icon = ICONS[type] ?? ImageIcon;
  return <Icon className={className} />;
}

/**
 * Thumbnail with honest fallbacks. Inspiration / external references are framed with a hatched
 * edge so they are never confused with the brand's own official material.
 */
export function AssetThumb({
  asset,
  className,
  fit = "cover",
  showDuration = true,
  size = "thumb",
}: {
  asset: Pick<AssetSummary, "title" | "asset_type" | "thumbnail_url" | "preview_url" | "duration_seconds" | "reference_role" | "dominant_colors">;
  className?: string;
  fit?: "cover" | "contain";
  showDuration?: boolean;
  size?: "thumb" | "preview";
}) {
  const [failed, setFailed] = React.useState(false);
  const src = size === "preview" ? asset.preview_url ?? asset.thumbnail_url : asset.thumbnail_url ?? asset.preview_url;
  const borrowed = asset.reference_role === "inspiration" || asset.reference_role === "external";
  return (
    <div
      className={cn(
        "relative overflow-hidden bg-sunken",
        borrowed && "outline outline-1 -outline-offset-1 outline-dashed outline-ink-2/40",
        className,
      )}
      style={!src && asset.dominant_colors?.length ? { background: asset.dominant_colors[0] } : undefined}
    >
      {src && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={asset.title}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className={cn("size-full", fit === "cover" ? "object-cover" : "object-contain")}
        />
      ) : (
        <div className="flex size-full items-center justify-center text-faint">
          <AssetTypeIcon type={asset.asset_type} className="size-6" />
        </div>
      )}
      {showDuration && asset.duration_seconds ? (
        <span className="tabular absolute bottom-1.5 right-1.5 rounded-[3px] bg-ink/75 px-1 text-2xs text-white">
          {formatDuration(asset.duration_seconds)}
        </span>
      ) : null}
    </div>
  );
}
