"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { useMe, useAuthRedirect } from "@/lib/session";
import { ApiError } from "@/lib/api";
import { LoadingBlock } from "@/components/page";

/** Entry point: platform administrators land in the console, customer users in their workspace. */
export default function Home() {
  useAuthRedirect();
  const router = useRouter();
  const me = useMe();
  React.useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace("/login");
    if (!me.data) return;
    if (me.data.user?.is_platform_admin) router.replace("/admin");
    else if (me.data.memberships?.length) router.replace(`/w/${me.data.memberships[0].slug}`);
    else router.replace("/no-access");
  }, [me.data, me.error, router]);
  return (
    <main className="mx-auto max-w-md p-10">
      <LoadingBlock rows={3} />
    </main>
  );
}
