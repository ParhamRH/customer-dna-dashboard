"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useAuthRedirect } from "@/lib/session";
import { useWorkspaceQuery } from "@/lib/workspace";
import { LoadingBlock } from "@/components/page";
import { Wordmark } from "@/components/wordmark";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  useAuthRedirect();
  const { org } = useParams<{ org: string }>();
  const ws = useWorkspaceQuery(org);
  if (ws.error) {
    const e = ws.error;
    const archived = e instanceof ApiError && e.status === 403;
    return (
      <main className="mx-auto grid min-h-dvh max-w-lg content-center gap-4 px-6">
        <Wordmark />
        <h1 className="mt-6 text-2xl font-semibold">{archived ? "This workspace is not available" : "Workspace not found"}</h1>
        <p className="text-md text-muted">
          {archived
            ? e.message
            : "It may not exist, or your account is not a member of it. Each customer library is only visible to its own members."}
        </p>
        <Link href="/" className="text-accent underline underline-offset-2">
          Go to your start page
        </Link>
      </main>
    );
  }
  if (!ws.data) {
    return (
      <div className="p-10">
        <LoadingBlock rows={5} />
      </div>
    );
  }
  return <>{children}</>;
}
