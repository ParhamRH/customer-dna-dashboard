"use client";
import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, MoreHorizontal, Search, ShieldPlus } from "lucide-react";
import { toast } from "sonner";
import { request, errorMessage } from "@/lib/api";
import type { Page, PlatformUser, RoleInfo } from "@/lib/types";
import { useMe } from "@/lib/session";
import { ROLE_LABELS } from "@/lib/labels";
import { relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, PageHeader, Panel, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Segmented } from "@/components/ui/tabs";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Status, Tag } from "@/components/status";
import { CopyValue } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

export default function UsersPage() {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const me = useMe();
  const [search, setSearch] = React.useState("");
  const [scope, setScope] = React.useState<"all" | "admins">("all");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [secret, setSecret] = React.useState<{ email: string; password: string } | null>(null);
  const users = useQuery({
    queryKey: ["admin", "users", search, scope],
    queryFn: () => request<Page<PlatformUser>>("/v1/platform/users", { params: { search: search || undefined, platform_admins_only: scope === "admins" || undefined, limit: 200 } }),
  });
  const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: () => request<{ items: RoleInfo[] }>("/v1/platform/roles") });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<PlatformUser> }) => request<PlatformUser>(`/v1/platform/users/${id}`, { method: "PATCH", body }),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`${u.email} updated`);
    },
  });
  const reset = useMutation({
    mutationFn: (u: PlatformUser) => request<{ temporary_password: string }>(`/v1/platform/users/${u.id}/reset-password`, { method: "POST" }).then((r) => ({ ...r, email: u.email })),
    onSuccess: (r) => setSecret({ email: r.email, password: r.temporary_password }),
  });
  const revoke = useMutation({
    mutationFn: (u: PlatformUser) => request<{ revoked: number }>(`/v1/platform/users/${u.id}/revoke-sessions`, { method: "POST" }),
    onSuccess: (r) => toast.success(`${r.revoked} session(s) signed out`),
  });

  const allPerms = React.useMemo(() => {
    const s = new Set<string>();
    roles.data?.items.forEach((r) => r.permissions.forEach((p) => s.add(p)));
    return [...s].sort();
  }, [roles.data]);

  return (
    <Main wide>
      <PageHeader
        title="Users & roles"
        description="Everyone with an account, across all customers. Workspace membership and roles are managed per customer; platform administrators can open every workspace."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <ShieldPlus /> Add platform administrator
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input className="pl-8" placeholder="Search name or e-mail" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search users" />
        </div>
        <Segmented label="Scope" value={scope} onChange={setScope} options={[{ value: "all", label: "Everyone" }, { value: "admins", label: "Platform administrators" }]} />
        <span className="ml-auto text-sm text-muted">{users.data ? `${users.data.total} accounts` : ""}</span>
      </div>
      {users.error ? <ErrorState error={users.error} /> : null}
      {!users.data ? (
        <LoadingBlock rows={6} />
      ) : (
        <Panel className="mb-10">
          <Table>
            <THead>
              <tr>
                <th>Person</th>
                <th>Access</th>
                <th>Account</th>
                <th>Last sign-in</th>
                <th className="text-right">Sessions</th>
                <th className="w-0" />
              </tr>
            </THead>
            <TBody>
              {users.data.items.map((u) => {
                const self = u.id === me.data?.user?.id;
                return (
                  <tr key={u.id} className="align-top">
                    <td>
                      <div className="font-medium">
                        {u.full_name || u.email} {self ? <span className="text-sm font-normal text-muted">(you)</span> : null}
                      </div>
                      <div className="text-sm text-muted">{u.email}</div>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1.5">
                        {u.is_platform_admin ? <Tag tone="accent">Platform administrator</Tag> : null}
                        {u.memberships.map((m) => (
                          <Link key={m.membership_id} href={`/admin/customers/${m.organization_id}`}>
                            <Tag tone="outline" className="hover:bg-sunken">
                              {m.organization_name} · {ROLE_LABELS[m.role] ?? m.role}
                              {m.status !== "active" ? " (suspended)" : ""}
                            </Tag>
                          </Link>
                        ))}
                        {!u.is_platform_admin && u.memberships.length === 0 ? <span className="text-sm text-muted">No workspace</span> : null}
                      </div>
                    </td>
                    <td>
                      <Status status={u.is_active ? "active" : "suspended"} label={u.is_active ? "Active" : "Deactivated"} />
                    </td>
                    <td className="whitespace-nowrap text-sm text-muted">{relativeTime(u.last_login_at)}</td>
                    <td className="tabular text-right">{u.active_sessions}</td>
                    <td>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="icon-sm" variant="ghost" aria-label={`Actions for ${u.email}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem
                            onSelect={async () => {
                              if (await confirm({ title: `Reset the password of ${u.email}?`, description: "A temporary password is issued and every open session is signed out.", confirmLabel: "Reset password" }))
                                reset.mutate(u);
                            }}
                          >
                            <KeyRound /> Reset password
                          </DropdownMenuItem>
                          <DropdownMenuItem onSelect={() => revoke.mutate(u)}>Sign out everywhere</DropdownMenuItem>
                          {!self ? (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onSelect={() => update.mutate({ id: u.id, body: { is_platform_admin: !u.is_platform_admin } })}>
                                {u.is_platform_admin ? "Remove platform administrator" : "Make platform administrator"}
                              </DropdownMenuItem>
                              <DropdownMenuItem destructive={u.is_active} onSelect={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                                {u.is_active ? "Deactivate account" : "Reactivate account"}
                              </DropdownMenuItem>
                            </>
                          ) : null}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        </Panel>
      )}

      <Section title="Roles and permissions" description="Fixed roles. A role's permissions apply inside one customer workspace; API tokens can be narrowed further with scopes.">
        {!roles.data ? (
          <LoadingBlock rows={4} />
        ) : (
          <Panel>
            <Table className="text-sm">
              <THead>
                <tr>
                  <th>Permission</th>
                  <th className="text-center">Platform administrator</th>
                  {roles.data.items.map((r) => (
                    <th key={r.key} className="text-center">
                      {ROLE_LABELS[r.key] ?? r.name}
                    </th>
                  ))}
                </tr>
              </THead>
              <TBody>
                {allPerms.map((p) => (
                  <tr key={p}>
                    <td className="font-mono text-[12px]">{p}</td>
                    <td className="text-center">
                      <Check className="mx-auto size-3.5 text-accent" aria-label="granted" />
                    </td>
                    {roles.data.items.map((r) => (
                      <td key={r.key} className="text-center">
                        {r.permissions.includes(p) ? <Check className="mx-auto size-3.5 text-accent" aria-label="granted" /> : <span className="text-faint" aria-label="not granted">·</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </TBody>
            </Table>
          </Panel>
        )}
      </Section>
      <CreateAdminDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={(email, pw) => pw && setSecret({ email, password: pw })} />
      <Dialog open={!!secret} onOpenChange={(o) => !o && setSecret(null)}>
        {secret ? (
          <DialogContent size="sm">
            <DialogHeader title="Temporary password" description={`For ${secret.email}. Shown once — share it securely.`} />
            <DialogBody>
              <CopyValue value={secret.password} className="text-sm" />
            </DialogBody>
            <DialogFooter>
              <Button variant="primary" onClick={() => setSecret(null)}>
                Done
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </Main>
  );
}

function CreateAdminDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (email: string, pw: string | null) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const create = useMutation({
    mutationFn: () => request<PlatformUser>("/v1/platform/users", { method: "POST", body: { email, full_name: name, is_platform_admin: true } }),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      onOpenChange(false);
      onCreated(u.email, u.temporary_password ?? null);
      setEmail("");
      setName("");
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader title="Add platform administrator" description="Platform administrators can open and manage every customer workspace." />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <DialogBody className="grid gap-3">
            <Field label="E-mail" htmlFor="pa-email">
              <Input id="pa-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="Full name" htmlFor="pa-name">
              <Input id="pa-name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            {create.error ? <p className="text-sm text-danger">{errorMessage(create.error)}</p> : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!email || create.isPending}>
              Add administrator
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
