"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { request, type RequestOptions } from "@/lib/api";
import type { Brand, Organization, Workspace } from "@/lib/types";

export type WorkspaceCtx = {
  orgSlug: string;
  orgId: string;
  org: Workspace["organization"];
  role: string;
  permissions: Set<string>;
  brands: Brand[];
  brand: Brand;
  /** Base path of the current brand: /w/<org>/<brand> */
  base: string;
  can: (perm: string) => boolean;
  /** API call scoped to this workspace (sends X-Organization-Id). */
  req: <T = unknown>(path: string, opts?: Omit<RequestOptions, "org">) => Promise<T>;
  /** Query key prefix, so cache entries can never mix customers. */
  key: (...parts: unknown[]) => unknown[];
};

const Ctx = React.createContext<WorkspaceCtx | null>(null);

export function useWorkspaceQuery(orgSlug: string) {
  return useQuery({
    queryKey: ["ws", orgSlug, "workspace"],
    queryFn: () => request<Workspace>("/v1/workspace", { org: orgSlug }),
    staleTime: 60_000,
  });
}

export function WorkspaceProvider({ value, children }: { value: WorkspaceCtx; children: React.ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function buildWorkspaceCtx(orgSlug: string, ws: Workspace, brand: Brand): WorkspaceCtx {
  const permissions = new Set(ws.permissions);
  return {
    orgSlug,
    orgId: ws.organization.id,
    org: ws.organization,
    role: ws.role,
    permissions,
    brands: ws.brands,
    brand,
    base: `/w/${orgSlug}/${brand.slug}`,
    can: (p) => permissions.has(p),
    req: (path, opts) => request(path, { ...opts, org: ws.organization.id }),
    key: (...parts) => ["ws", orgSlug, ...parts],
  };
}

export function useWorkspace(): WorkspaceCtx {
  const v = React.useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside a workspace");
  return v;
}

export function isFullOrg(o: Workspace["organization"]): o is Organization {
  return "status" in o;
}
