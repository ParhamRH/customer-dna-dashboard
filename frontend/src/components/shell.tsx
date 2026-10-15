"use client";
import * as React from "react";
import { useOnChange } from "@/lib/state";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Menu, Monitor, Moon, Sun, X } from "lucide-react";
import { cn, initials } from "@/lib/utils";
import { logout, useMe } from "@/lib/session";
import { useTheme } from "@/lib/providers";
import { ROLE_LABELS } from "@/lib/labels";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function UserMenu({ tone = "light", role }: { tone?: "light" | "console"; role?: string }) {
  const me = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const { theme, setTheme } = useTheme();
  const u = me.data?.user;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left outline-none focus-visible:outline-2 focus-visible:outline-ring",
          tone === "console" ? "hover:bg-white/8" : "hover:bg-sunken",
        )}
        aria-label="Account menu"
      >
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
            tone === "console" ? "bg-console-2 text-console-ink" : "bg-ink text-paper",
          )}
        >
          {initials(u?.full_name || u?.email)}
        </span>
        <span className="min-w-0 flex-1">
          <span className={cn("block truncate text-sm font-medium", tone === "console" ? "text-console-ink" : "text-ink")}>
            {u?.full_name || u?.email || "…"}
          </span>
          <span className={cn("block truncate text-xs", tone === "console" ? "text-console-muted" : "text-muted")}>
            {role ? ROLE_LABELS[role] ?? role : u?.email}
          </span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60">
        <DropdownMenuLabel>{u?.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        {(
          [
            ["light", "Light", Sun],
            ["dark", "Dark", Moon],
            ["system", "Match system", Monitor],
          ] as const
        ).map(([v, label, Icon]) => (
          <DropdownMenuItem key={v} onSelect={() => setTheme(v)} className={theme === v ? "font-medium" : ""}>
            <Icon /> {label}
            {theme === v ? <span className="ml-auto text-xs text-muted">current</span> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/account">Account & password</Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={async () => {
            await logout();
            qc.clear();
            router.replace("/login");
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function NavLink({
  href,
  children,
  active,
  tone = "light",
  badge,
  onNavigate,
}: {
  href: string;
  children: React.ReactNode;
  active: boolean;
  tone?: "light" | "console";
  badge?: React.ReactNode;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex h-7 items-center gap-2 rounded-md px-2 text-base transition-colors",
        tone === "console"
          ? active
            ? "bg-white/10 font-medium text-console-ink"
            : "text-console-muted hover:bg-white/6 hover:text-console-ink"
          : active
            ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_var(--line)]"
            : "text-ink-2 hover:bg-sunken hover:text-ink",
      )}
    >
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {badge}
    </Link>
  );
}

/** Responsive two-column frame: fixed sidebar on desktop, slide-over on small screens. */
export function AppFrame({
  sidebar,
  children,
  tone = "light",
  banner,
}: {
  sidebar: (close: () => void) => React.ReactNode;
  children: React.ReactNode;
  tone?: "light" | "console";
  banner?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();
  useOnChange(pathname, () => setOpen(false)); // close the mobile menu after navigating
  const side = cn(
    "flex h-full w-64 shrink-0 flex-col overflow-y-auto",
    tone === "console" ? "bg-console text-console-ink" : "border-r border-line bg-surface-2",
  );
  return (
    <div className="flex min-h-dvh flex-col">
      {banner}
      <div className="flex min-h-0 flex-1">
        <aside className={cn(side, "sticky top-0 hidden h-dvh lg:flex")}>{sidebar(() => setOpen(false))}</aside>
        {open ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} />
            <aside className={cn(side, "relative z-10 h-dvh shadow-pop")}>
              <button className="absolute right-2 top-2 rounded p-1 opacity-70 hover:opacity-100" onClick={() => setOpen(false)} aria-label="Close navigation">
                <X className="size-4" />
              </button>
              {sidebar(() => setOpen(false))}
            </aside>
          </div>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex h-11 items-center border-b border-line px-4 lg:hidden">
            <button onClick={() => setOpen(true)} className="-ml-1 rounded p-1 hover:bg-sunken" aria-label="Open navigation">
              <Menu className="size-5" />
            </button>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

export function Main({ children, className, wide }: { children: React.ReactNode; className?: string; wide?: boolean }) {
  return <main className={cn("mx-auto w-full min-w-0 px-5 py-7 sm:px-8", wide ? "max-w-[1600px]" : "max-w-6xl", className)}>{children}</main>;
}

export function CountBadge({ n, tone = "default" }: { n?: number; tone?: "default" | "ai" | "console" }) {
  if (!n) return null;
  return (
    <span
      className={cn(
        "tabular ml-auto min-w-5 rounded-full px-1.5 text-center text-2xs leading-4",
        tone === "ai" ? "border border-dashed border-ai-line bg-ai-soft text-ai" : tone === "console" ? "bg-white/12 text-console-ink" : "bg-sunken text-ink-2",
      )}
    >
      {n > 999 ? "999+" : n}
    </span>
  );
}

export function useActive() {
  const pathname = usePathname();
  return (href: string, exact = false) => (exact ? pathname === href : pathname === href || pathname.startsWith(href + "/"));
}
