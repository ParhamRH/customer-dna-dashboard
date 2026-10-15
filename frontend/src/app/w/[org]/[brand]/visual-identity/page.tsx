"use client";
import Link from "next/link";
import { useWorkspace } from "@/lib/workspace";
import { useDomain } from "@/lib/hooks";
import { DomainPage } from "@/components/knowledge/domain-page";
import { PalettesSection } from "@/components/visual/palettes";
import { TypographySection } from "@/components/visual/typography";
import { TokensSection } from "@/components/visual/tokens";
import { Section } from "@/components/page";
import { AssetThumb } from "@/components/asset-thumb";
import { Status } from "@/components/status";

function Logos() {
  const ws = useWorkspace();
  const d = useDomain("visual_identity");
  const logos = d.data?.logos ?? [];
  return (
    <Section
      title="Logos"
      description="Logo files live in the asset library (type “Logo”); usage rules are documented below."
      actions={
        <Link href={`${ws.base}/assets?asset_type=logo`} className="text-sm text-accent hover:underline">
          Manage logo files
        </Link>
      }
    >
      {logos.length ? (
        <div className="flex flex-wrap gap-4">
          {logos.map((a) => (
            <Link key={a.id} href={`${ws.base}/assets/${a.id}`} className="group w-52">
              <AssetThumb asset={a} fit="contain" className="aspect-[4/3] rounded-md border border-line bg-[repeating-conic-gradient(var(--sunken)_0_25%,var(--surface)_0_50%)] bg-[length:16px_16px] p-4" />
              <span className="mt-1.5 flex items-center justify-between gap-2 text-sm">
                <span className="truncate group-hover:underline">{a.title}</span>
                <Status status={a.approval_status} />
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-base text-muted">No logo files yet. Upload them to the asset library with the type “Logo”.</p>
      )}
    </Section>
  );
}

export default function VisualIdentityPage() {
  return (
    <DomainPage
      domain="visual_identity"
      wide
      intro="Logos, color, typography and the graphic system — with HEX, RGB, HSL, OKLCH and CMYK values and exports for developers and design tools."
      before={
        <>
          <Logos />
          <PalettesSection />
          <TypographySection />
        </>
      }
      after={<TokensSection domain="visual_identity" title="Visual identity tokens" />}
    />
  );
}
