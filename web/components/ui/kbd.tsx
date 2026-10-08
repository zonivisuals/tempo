import * as React from "react";

import { cn } from "@/utils/cn";

export function Kbd({ className, children, ...rest }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-6 min-w-6 items-center justify-center rounded border border-stroke-soft-200 bg-bg-weak-50 px-1.5 font-mono text-label-sm text-text-sub-600",
        className,
      )}
      {...rest}
    >
      {children}
    </kbd>
  );
}
