"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { request, setUnauthorizedHandler } from "@/lib/api";
import type { Me } from "@/lib/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => request<Me>("/v1/auth/me"), staleTime: 60_000 });
}

/** Sends the user to the sign-in page whenever the API answers 401 (expired or revoked session). */
export function useAuthRedirect() {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  React.useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.clear();
      const next = path && path !== "/login" ? `?next=${encodeURIComponent(path)}` : "";
      router.replace(`/login${next}`);
    });
  }, [router, path, qc]);
}

export async function logout() {
  try {
    await request("/v1/auth/logout", { method: "POST" });
  } catch {
    /* already signed out */
  }
}
