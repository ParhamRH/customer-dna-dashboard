"use client";
import * as React from "react";
import { Tooltip as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const TooltipProvider = T.Provider;

export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  if (!content) return <>{children}</>;
  return (
    <T.Root delayDuration={250}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className={cn("z-50 max-w-72 rounded-md bg-ink px-2 py-1 text-sm text-paper shadow-pop data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0")}>
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
