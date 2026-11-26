import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx } from "clsx";
import type { ComponentProps } from "react";

const variant = cva("button", {
  variants: { variant: { primary: "button-primary", outline: "button-outline", ghost: "button-ghost" } },
  defaultVariants: { variant: "primary" },
});

export function Button({ asChild, className, variant: appearance, ...props }:
  ComponentProps<"button"> & VariantProps<typeof variant> & { asChild?: boolean }) {
  const Component = asChild ? Slot : "button";
  return <Component className={clsx(variant({ variant: appearance }), className)} {...props} />;
}
