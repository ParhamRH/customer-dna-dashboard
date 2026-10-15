"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { ArrowLeftRight, ChevronsUpDown, Plus, Search, ShieldAlert } from "lucide-react";
import { useMe } from "@/lib/session";
import { buildWorkspaceCtx, useWorkspace, useWorkspaceQuery, WorkspaceProvider } from "@/lib/workspace";
import { usePalettes, useReviewSummary, reviewTotal } from "@/lib/hooks";
import { WORKSPACE_NAV } from "@/lib/labels";
import { AppFrame, CountBadge, NavLink, UserMenu, useActive } from "@/components/shell";
import { DnaStrip, stripFromPalettes } from "@/components/dna-strip";
import { EmptyState, LoadingBlock } from "@/components/page";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Mark } from "@/components/wordmark";

function BrandSwitcher() {
  const ws = useWorkspace();
  const me = useMe();
  const router = useRouter();
  const others = me.data?.memberships?.filter((m) => m.slug !== ws.orgSlug) ?? [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-sunken focus-visible:outline-2 focus-visible:outline-ring">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs text-muted">{ws.org.name}</span>
          <span className="block truncate text-lg font-semibold leading-tight text-ink">{ws.brand.name}</span>
        </span>
        <ChevronsUpDown className="mt-1 size-4 shrink-0 text-faint group-hover:text-muted" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Brands of {ws.org.name}</DropdownMenuLabel>
        {ws.brands.map((b) => (
          <DropdownMenuItem key={b.id} onSelect={() => router.push(`/w/${ws.orgSlug}/${b.slug}`)} className={b.id === ws.brand.id ? "font-medium" : ""}>
            {b.name}
            {b.status === "archived" ? <span className="ml-auto text-xs text-muted">archived</span> : null}
          </DropdownMenuItem>
        ))}
        {ws.can("brand.manage") ? (
          <DropdownMenuItem onSelect={() => router.push(`${ws.base}/settings?tab=brands`)}>
            <Plus /> New brand
          </DropdownMenuItem>
        ) : null}
        {others.length ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Other workspaces</DropdownMenuLabel>
            {others.map((m) => (
              <DropdownMenuItem key={m.organization_id} onSelect={() => router.push(`/w/${m.slug}`)}>
                <ArrowLeftRight /> {m.name}
              </DropdownMenuItem>
            ))}
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WorkspaceSidebar({ close }: { close: () => void }) {
  const ws = useWorkspace();
  const router = useRouter();
  const active = useActive();
  const palettes = usePalettes();
  const review = useReviewSummary();
  const pending = reviewTotal(review.data);
  const [q, setQ] = React.useState("");
  const isAdmin = ws.role === "platform_super_admin";
  return (
    <div className="flex h-full flex-col gap-4 px-3 py-4">
      <div className="grid gap-2">
        <BrandSwitcher />
        <div className="px-2">
          <DnaStrip colors={stripFromPalettes(palettes.data?.items)} height={8} interactive label={ws.brand.name} />
        </div>
      </div>
      {ws.can("search.use") ? (
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            router.push(`${ws.base}/search?q=${encodeURIComponent(q)}`);
            close();
          }}
          className="relative px-1"
        >
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search this library" className="h-7 pl-7 text-sm" aria-label="Search this library" />
        </form>
      ) : null}
      <nav aria-label="Workspace" className="grid gap-4">
        {WORKSPACE_NAV.map((group) => {
          const items = group.items.filter((i) => !i.perm || ws.can(i.perm));
          if (!items.length) return null;
          return (
            <div key={group.label} className="grid gap-0.5">
              <p className="px-2 pb-0.5 text-xs text-muted">{group.label}</p>
              {items.map((item) => {
                const href = `${ws.base}${item.path}`;
                return (
                  <NavLink
                    key={item.key}
                    href={href}
                    onNavigate={close}
                    active={item.path === "" ? active(href, true) : active(href)}
                    badge={item.key === "review" ? <CountBadge tone="ai" n={pending} /> : undefined}
                  >
                    {item.label}
                  </NavLink>
                );
              })}
            </div>
          );
        })}
      </nav>
      <div className="mt-auto grid gap-1 border-t border-line pt-3">
        {isAdmin ? (
          <Link href="/admin" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink-2 hover:bg-sunken">
            <Mark className="h-3 w-4" /> Platform console
          </Link>
        ) : null}
        <UserMenu role={ws.role} />
      </div>
    </div>
  );
}

function AdminBand() {
  const ws = useWorkspace();
  if (ws.role !== "platform_super_admin") return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-console px-4 py-1.5 text-sm text-console-ink" role="status">
      <ShieldAlert className="size-4 text-console-muted" />
      <span>
        You are inside <b className="font-semibold">{ws.org.name}</b>&apos;s workspace as platform administrator. Every change is recorded under your name.
      </span>
      <Link href="/admin/customers" className="ml-auto text-console-muted underline-offset-2 hover:text-console-ink hover:underline">
        Return to console
      </Link>
    </div>
  );
}

export default function BrandLayout({ children }: { children: React.ReactNode }) {
  const { org, brand } = useParams<{ org: string; brand: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const ws = useWorkspaceQuery(org);
  const first = ws.data?.brands.find((b) => b.status === "active") ?? ws.data?.brands[0];
  const current = ws.data?.brands.find((b) => b.slug === brand || b.id === brand);

  React.useEffect(() => {
    // "_" (or an unknown brand) resolves to the first brand, keeping the rest of the path.
    if (ws.data && !current && first) {
      const rest = pathname.split("/").slice(4).join("/");
      router.replace(`/w/${org}/${first.slug}${rest ? "/" + rest : ""}`);
    }
  }, [ws.data, current, first, pathname, org, router]);

  const ctx = React.useMemo(() => (ws.data && current ? buildWorkspaceCtx(org, ws.data, current) : null), [ws.data, current, org]);
  if (!ws.data) return <LoadingBlock className="p-10" />;
  if (!ctx) {
    return first ? (
      <LoadingBlock className="p-10" />
    ) : (
      <main className="mx-auto max-w-xl p-10">
        <EmptyState title="This workspace has no brand yet" />
      </main>
    );
  }
  return (
    <WorkspaceProvider value={ctx}>
      <AppFrame banner={<AdminBand />} sidebar={(close) => <WorkspaceSidebar close={close} />}>
        <React.Suspense fallback={<LoadingBlock className="p-10" />}>{children}</React.Suspense>
      </AppFrame>
    </WorkspaceProvider>
  );
}
