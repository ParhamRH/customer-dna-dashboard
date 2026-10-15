"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, MoreHorizontal, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { request, errorMessage } from "@/lib/api";
import type { Member } from "@/lib/types";
import { ORG_ROLES, ROLE_LABELS, ROLE_SUMMARY } from "@/lib/labels";
import { relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { TBody, THead, Table } from "@/components/ui/misc";
import { EmptyState, ErrorState, LoadingBlock, Panel } from "@/components/page";
import { Status } from "@/components/status";
import { CopyValue } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";

type MembersResponse = { items: Member[]; roles: { key: string; permissions: string[] }[] };

/** Workspace members for one organization (used in workspace settings and in the platform console). */
export function MembersManager({ org, canManage }: { org: string; canManage: boolean }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const key = ["ws", org, "members"];
  const q = useQuery({ queryKey: key, queryFn: () => request<MembersResponse>("/v1/workspace/members", { org }) });
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Pick<Member, "role" | "status">> }) =>
      request<Member>(`/v1/workspace/members/${id}`, { method: "PATCH", body, org }),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(`${m.email} updated`);
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => request(`/v1/workspace/members/${id}`, { method: "DELETE", org }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      toast.success("Member removed");
    },
  });

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingBlock rows={4} />;
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      {canManage ? (
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => setInviteOpen(true)}>
            <UserPlus /> Add member
          </Button>
        </div>
      ) : null}
      {q.data.items.length === 0 ? (
        <EmptyState title="No members yet">Add the people who will curate this brand library.</EmptyState>
      ) : (
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last sign-in</th>
                {canManage ? (
                  <th className="w-0">
                    <span className="sr-only">Actions</span>
                  </th>
                ) : null}
              </tr>
            </THead>
            <TBody>
              {q.data.items.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div className="font-medium">{m.full_name || m.email}</div>
                    <div className="text-sm text-muted">{m.email}</div>
                  </td>
                  <td>
                    {canManage ? (
                      <NativeSelect
                        aria-label={`Role of ${m.email}`}
                        className="h-7 w-48 text-sm"
                        value={m.role}
                        onChange={(e) => update.mutate({ id: m.id, body: { role: e.target.value } })}
                      >
                        {ORG_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABELS[r]}
                          </option>
                        ))}
                      </NativeSelect>
                    ) : (
                      ROLE_LABELS[m.role] ?? m.role
                    )}
                  </td>
                  <td>
                    <Status status={m.status} />
                  </td>
                  <td className="text-sm text-muted">{relativeTime(m.last_login_at)}</td>
                  {canManage ? (
                    <td>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="icon-sm" variant="ghost" aria-label={`Actions for ${m.email}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onSelect={() => update.mutate({ id: m.id, body: { status: m.status === "active" ? "suspended" : "active" } })}>
                            {m.status === "active" ? "Suspend access" : "Restore access"}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            destructive
                            onSelect={async () => {
                              if (
                                await confirm({
                                  title: `Remove ${m.email}?`,
                                  description: "They lose access to this workspace immediately. Their past actions stay in the audit log.",
                                  confirmLabel: "Remove member",
                                  destructive: true,
                                })
                              )
                                remove.mutate(m.id);
                            }}
                          >
                            Remove from workspace
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  ) : null}
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      )}
      <RolesReference roles={q.data.roles} />
      <InviteDialog org={org} open={inviteOpen} onOpenChange={setInviteOpen} />
    </div>
  );
}

function RolesReference({ roles }: { roles: MembersResponse["roles"] }) {
  return (
    <details className="group rounded-lg border border-line bg-surface px-4 py-3 text-base">
      <summary className="cursor-pointer select-none font-medium">What each role can do</summary>
      <dl className="mt-3 grid gap-3">
        {roles.map((r) => (
          <div key={r.key} className="grid gap-1 sm:grid-cols-[12rem_1fr]">
            <dt className="font-medium">{ROLE_LABELS[r.key] ?? r.key}</dt>
            <dd>
              <p className="text-ink-2">{ROLE_SUMMARY[r.key]}</p>
              <p className="mt-1 text-sm text-muted">{r.permissions.join(", ")}</p>
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function InviteDialog({ org, open, onOpenChange }: { org: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [role, setRole] = React.useState("editor");
  const [result, setResult] = React.useState<Member | null>(null);
  const add = useMutation({
    mutationFn: () => request<Member>("/v1/workspace/members", { method: "POST", body: { email, full_name: name, role }, org }),
    onSuccess: (m) => {
      setResult(m);
      qc.invalidateQueries({ queryKey: ["ws", org, "members"] });
    },
    onError: () => {},
  });
  const close = (o: boolean) => {
    if (!o) {
      setEmail("");
      setName("");
      setRole("editor");
      setResult(null);
      add.reset();
    }
    onOpenChange(o);
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent size="sm">
        <DialogHeader title={result ? "Member added" : "Add member"} description={result ? undefined : "Existing accounts keep their password. New accounts get a temporary one."} />
        {result ? (
          <>
            <DialogBody className="grid gap-3 text-base">
              <p>
                {result.email} is now a {ROLE_LABELS[result.role]?.toLowerCase()} in this workspace.
              </p>
              {result.temporary_password ? (
                <div className="rounded-md border border-line bg-surface-2 p-3">
                  <p className="flex items-center gap-2 font-medium">
                    <KeyRound className="size-4" /> Temporary password
                  </p>
                  <p className="mt-1 text-sm text-muted">Shown once. Share it securely; it should be changed at first sign-in.</p>
                  <CopyValue value={result.temporary_password} className="mt-2 text-sm" />
                </div>
              ) : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="primary" onClick={() => close(false)}>
                Done
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate();
            }}
          >
            <DialogBody className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
              <Field label="E-mail" htmlFor="inv-email">
                <Input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
              </Field>
              <Field label="Full name" htmlFor="inv-name">
                <Input id="inv-name" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Role" htmlFor="inv-role" hint={ROLE_SUMMARY[role]}>
                <NativeSelect id="inv-role" value={role} onChange={(e) => setRole(e.target.value)}>
                  {ORG_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              {add.error ? <p className="text-sm text-danger">{errorMessage(add.error)}</p> : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="ghost" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={!email || add.isPending}>
                {add.isPending ? "Adding…" : "Add member"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
