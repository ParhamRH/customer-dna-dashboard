"use client";
import { DomainPage } from "@/components/knowledge/domain-page";
import { TokensSection } from "@/components/visual/tokens";

export default function DesignLanguagePage() {
  return (
    <DomainPage
      domain="design_language"
      intro="Layout, grid, spacing, hierarchy, components, interaction and motion — with design tokens developers and design tools can consume directly."
      after={<TokensSection domain="design_language" />}
    />
  );
}
