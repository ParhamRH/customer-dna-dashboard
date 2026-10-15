import * as React from "react";
import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-ink hover:bg-accent-hover",
        secondary: "border border-line-strong bg-surface text-ink hover:bg-surface-2",
        ghost: "text-ink-2 hover:bg-sunken hover:text-ink",
        danger: "bg-danger text-white hover:opacity-90",
        "danger-outline": "border border-danger/40 bg-surface text-danger hover:bg-danger-soft",
        link: "text-accent underline-offset-2 hover:underline px-0 h-auto",
        console: "text-console-ink/80 hover:bg-white/8 hover:text-console-ink",
      },
      size: {
        sm: "h-7 px-2.5 text-sm",
        md: "h-8 px-3 text-base",
        lg: "h-10 px-4 text-md",
        icon: "size-8",
        "icon-sm": "size-7",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot.Root : "button";
    return <Comp ref={ref} type={asChild ? undefined : (type ?? "button")} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";

export { buttonVariants };
