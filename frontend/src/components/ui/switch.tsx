"use client";
import * as React from "react";
import { Switch as SwitchPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";

export const Switch = React.forwardRef<
  React.ComponentRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      "inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-line-strong transition-colors data-[state=checked]:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="pointer-events-none block size-3.5 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-[15px] data-[state=unchecked]:translate-x-[1px]" />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";
