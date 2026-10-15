"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCustomers } from "@/lib/admin";
import { ADMIN_NAV } from "@/lib/labels";
import { useAuthRedirect, useMe } from "@/lib/session";
import { AppFrame, CountBadge, NavLink, UserMenu, useActive } from "@/components/shell";
import { Wordmark } from "@/components/wordmark";
import { DnaStrip } from "@/components/dna-strip";
import { LoadingBlock } from "@/components/page";

function AdminSidebar({ close }: { close: () => void }) {
  const active = useActive();
  const customers = useCustomers();
  const pending = customers.data?.items.reduce((s, c) => s + c.pending_reviews, 0) ?? 0;
  return (
    <div className="flex h-full flex-col gap-6 px-3 py-4">
      <Link href="/admin" className="px-2 text-console-ink" onClick={close}>
        <Wordmark />
      </Link>
      <nav aria-label="Platform administration" className="grid gap-0.5">
        <p className="px-2 pb-1 text-xs text-console-muted">Platform console</p>
        {ADMIN_NAV.map((item) => (
          <NavLink
            key={item.key}
            tone="console"
            href={item.path}
            active={item.path === "/admin" ? active("/admin", true) : active(item.path)}
            onNavigate={close}
            badge={item.key === "processing" ? <CountBadge tone="console" n={pending} /> : undefined}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <nav aria-label="Customer workspaces" className="grid gap-0.5">
        <p className="px-2 pb-1 text-xs text-console-muted">Open a workspace</p>
        {customers.data?.items
          .filter((c) => c.status !== "pending_deletion")
          .map((c) => (
            <Link
              key={c.id}
              href={`/w/${c.slug}`}
              onClick={close}
              className="group rounded-md px-2 py-1.5 text-console-muted hover:bg-white/6 hover:text-console-ink"
            >
              <span className="flex items-center justify-between gap-2 text-base">
                <span className="truncate">{c.name}</span>
                {c.status === "archived" ? <span className="text-2xs text-console-muted">archived</span> : null}
              </span>
              <DnaStrip colors={c.palette.map((p) => ({ hex: p.hex, name: p.name, weight: p.role === "primary" ? 3 : 1 }))} height={3} className="mt-1 opacity-80 group-hover:opacity-100" label={c.name} />
            </Link>
          ))}
      </nav>
      <div className="mt-auto">
        <UserMenu tone="console" role="platform_super_admin" />
      </div>
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  useAuthRedirect();
  const me = useMe();
  const router = useRouter();
  const isAdmin = me.data?.user?.is_platform_admin;
  React.useEffect(() => {
    if (me.data && !isAdmin) router.replace("/");
  }, [me.data, isAdmin, router]);
  if (!me.data || !isAdmin) {
    return (
      <div className="p-10">
        <LoadingBlock />
      </div>
    );
  }
  return (
    <AppFrame tone="console" sidebar={(close) => <AdminSidebar close={close} />}>
      {children}
    </AppFrame>
  );
}
