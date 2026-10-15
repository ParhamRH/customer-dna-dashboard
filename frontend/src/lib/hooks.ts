"use client";
/* Workspace-scoped data hooks. Every key starts with ["ws", <org>] so caches never mix customers. */
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/lib/workspace";
import type {
  AssetSummary,
  ContrastPair,
  Brand,
  BrandOverview,
  BrandVersion,
  Collection,
  Concept,
  DesignToken,
  DomainView,
  Guideline,
  Palette,
  Principle,
  Project,
  Registry,
  Typography,
} from "@/lib/types";

export function useRegistry() {
  const ws = useWorkspace();
  return useQuery({ queryKey: ws.key("registry"), queryFn: () => ws.req<Registry>("/v1/knowledge/registry"), staleTime: 300_000 });
}

export function useBrandDetail() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("brand", ws.brand.id),
    queryFn: () => ws.req<Brand & { overview: BrandOverview }>(`/v1/brands/${ws.brand.id}`),
  });
}

export function usePalettes(brandId?: string) {
  const ws = useWorkspace();
  const id = brandId ?? ws.brand.id;
  return useQuery({
    queryKey: ws.key("palettes", id),
    queryFn: () => ws.req<{ items: Palette[]; accessibility: ContrastPair[] }>(`/v1/brands/${id}/palettes`),
    enabled: ws.can("knowledge.read"),
  });
}

export function useTypography() {
  const ws = useWorkspace();
  return useQuery({ queryKey: ws.key("typography", ws.brand.id), queryFn: () => ws.req<{ items: Typography[] }>(`/v1/brands/${ws.brand.id}/typography`) });
}

export function useDesignTokens() {
  const ws = useWorkspace();
  return useQuery({ queryKey: ws.key("tokens", ws.brand.id), queryFn: () => ws.req<{ items: DesignToken[] }>(`/v1/brands/${ws.brand.id}/design-tokens`) });
}

export function useDomain(domain: string) {
  const ws = useWorkspace();
  return useQuery({ queryKey: ws.key("domain", ws.brand.id, domain), queryFn: () => ws.req<DomainView>(`/v1/brands/${ws.brand.id}/domains/${domain}`) });
}

export function useConcepts() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("knowledge", ws.brand.id, "concepts"),
    queryFn: () => ws.req<{ items: Concept[] }>(`/v1/brands/${ws.brand.id}/knowledge/concepts`),
  });
}

export function usePrinciples() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("knowledge", ws.brand.id, "principles"),
    queryFn: () => ws.req<{ items: Principle[] }>(`/v1/brands/${ws.brand.id}/knowledge/principles`),
  });
}

export function useGuidelines() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("knowledge", ws.brand.id, "guidelines"),
    queryFn: () => ws.req<{ items: Guideline[] }>(`/v1/brands/${ws.brand.id}/knowledge/guidelines`),
  });
}

export function useCollections() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("collections", ws.brand.id),
    queryFn: () => ws.req<{ items: Collection[] }>(`/v1/brands/${ws.brand.id}/collections`),
    enabled: ws.can("assets.read"),
  });
}

export function useProjects() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("projects", ws.brand.id),
    queryFn: () => ws.req<{ items: Project[]; project_types: string[] }>(`/v1/brands/${ws.brand.id}/projects`),
  });
}

export function useVersions() {
  const ws = useWorkspace();
  return useQuery({ queryKey: ws.key("versions", ws.brand.id), queryFn: () => ws.req<{ items: BrandVersion[] }>(`/v1/brands/${ws.brand.id}/versions`) });
}

export function useReviewSummary() {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("review", "summary", ws.brand.id),
    queryFn: () =>
      ws.req<{ analyses: Record<string, number>; suggestions: Record<string, number>; suggested_tags: number }>("/v1/review/summary", {
        params: { brand_id: ws.brand.id },
      }),
    enabled: ws.can("review.read"),
    refetchInterval: 30_000,
  });
}

export function reviewTotal(s?: { analyses: Record<string, number>; suggestions: Record<string, number> }) {
  if (!s) return 0;
  return Object.values(s.analyses).reduce((a, b) => a + b, 0) + Object.values(s.suggestions).reduce((a, b) => a + b, 0);
}

export function useAssetPicker(q: string, enabled = true) {
  const ws = useWorkspace();
  return useQuery({
    queryKey: ws.key("assets", "picker", ws.brand.id, q),
    queryFn: () => ws.req<{ items: AssetSummary[]; total: number }>("/v1/assets", { params: { brand_id: ws.brand.id, q: q || undefined, limit: 60 } }),
    enabled: enabled && ws.can("assets.read"),
  });
}

/** user_id → display name, when the viewer may list members (otherwise falls back to "a member"). */
export function useMemberNames() {
  const ws = useWorkspace();
  const q = useQuery({
    queryKey: ws.key("members"),
    queryFn: () => ws.req<{ items: { user_id: string; full_name: string; email: string }[] }>("/v1/workspace/members"),
    enabled: ws.can("users.read"),
    staleTime: 120_000,
  });
  return (id: string | null | undefined) => {
    if (!id) return "—";
    const m = q.data?.items.find((x) => x.user_id === id);
    return m ? m.full_name || m.email : ws.role === "platform_super_admin" ? "Platform administrator" : "a member";
  };
}
