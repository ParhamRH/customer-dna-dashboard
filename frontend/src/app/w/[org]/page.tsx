"use client";
import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { useWorkspaceQuery } from "@/lib/workspace";
import { EmptyState, LoadingBlock } from "@/components/page";

export default function OrgIndex() {
  const { org } = useParams<{ org: string }>();
  const router = useRouter();
  const ws = useWorkspaceQuery(org);
  const first = ws.data?.brands.find((b) => b.status === "active") ?? ws.data?.brands[0];
  React.useEffect(() => {
    if (first) router.replace(`/w/${org}/${first.slug}`);
  }, [first, org, router]);
  if (ws.data && !first) {
    return (
      <main className="mx-auto max-w-xl p-10">
        <EmptyState title="This workspace has no brand yet">
          A customer administrator or creative director can create the first brand from the workspace settings.
        </EmptyState>
      </main>
    );
  }
  return (
    <div className="p-10">
      <LoadingBlock />
    </div>
  );
}
