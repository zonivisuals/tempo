// AlignUI-style Tag, Tempo palette
import * as React from "react";

import { cn } from "@/utils/cn";
import { tv, type VariantProps } from "@/utils/tv";

const tagVariants = tv({
  base: [
    "inline-flex items-center gap-1 rounded-full px-2.5 py-1",
    "text-subheading-2xs uppercase",
  ],
  variants: {
    tone: {
      orange: "bg-tag-orange-bg text-tag-orange-fg",
      blue: "bg-tag-blue-bg text-tag-blue-fg",
      green: "bg-tag-green-bg text-tag-green-fg",
      yellow: "bg-tag-yellow-bg text-tag-yellow-fg",
      neutral: "bg-bg-soft-200 text-text-sub-600",
    },
  },
  defaultVariants: {
    tone: "neutral",
  },
});

type TagProps = React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof tagVariants>;

export function Tag({ className, tone, ...rest }: TagProps) {
  return <span className={tagVariants({ tone, class: className })} {...rest} />;
}

export function TagDot({ className, ...rest }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("size-1.5 rounded-full bg-current", className)}
      aria-hidden="true"
      {...rest}
    />
  );
}
