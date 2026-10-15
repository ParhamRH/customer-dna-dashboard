"use client";
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { CustomerRow } from "@/lib/types";

export function useCustomers(params?: { search?: string; status?: string }) {
  return useQuery({
    queryKey: ["admin", "customers", params ?? {}],
    queryFn: () => request<{ items: CustomerRow[]; total: number }>("/v1/organizations", { params }),
  });
}
