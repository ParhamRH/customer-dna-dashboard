"use client";
import * as React from "react";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type ConfirmOptions = {
  title: string;
  description?: React.ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  /** Require the user to type this exact text (irreversible actions). */
  typeToConfirm?: string;
};

const Ctx = React.createContext<(o: ConfirmOptions) => Promise<boolean>>(async () => false);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);
  const [typed, setTyped] = React.useState("");
  const confirm = React.useCallback(
    (o: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setTyped("");
        setState({ ...o, resolve });
      }),
    [],
  );
  const close = (v: boolean) => {
    state?.resolve(v);
    setState(null);
  };
  const blocked = !!state?.typeToConfirm && typed !== state.typeToConfirm;
  return (
    <Ctx.Provider value={confirm}>
      {children}
      <Dialog open={!!state} onOpenChange={(o) => !o && close(false)}>
        {state ? (
          <DialogContent size="sm">
            <DialogHeader title={state.title} />
            <DialogBody className="grid gap-3 text-base text-ink-2">
              {state.description}
              {state.typeToConfirm ? (
                <label className="grid gap-1.5 text-sm">
                  <span>
                    Type <span className="font-mono text-ink">{state.typeToConfirm}</span> to confirm
                  </span>
                  <Input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} />
                </label>
              ) : null}
            </DialogBody>
            <DialogFooter>
              <Button variant="ghost" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button variant={state.destructive ? "danger" : "primary"} disabled={blocked} onClick={() => close(true)}>
                {state.confirmLabel}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </Ctx.Provider>
  );
}

export function useConfirm() {
  return React.useContext(Ctx);
}
