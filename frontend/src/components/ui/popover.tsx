"use client";
import * as React from "react";
import { Popover as P } from "radix-ui";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverClose = P.Close;

export function PopoverContent({ className, align = "start", sideOffset = 6, ...props }: React.ComponentPropsWithoutRef<typeof P.Content>) {
  return (
    <P.Portal>
      <P.Content
        align={align}
        sideOffset={sideOffset}
        className={cn("z-50 w-72 rounded-md border border-line bg-surface p-3 shadow-pop outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0", className)}
        {...props}
      />
    </P.Portal>
  );
}
