import * as React from "react";

import { cn } from "@/utils/cn";

export function Container({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("mx-auto w-full max-w-5xl px-6", className)} {...rest}>
      {children}
    </div>
  );
}

export function Section({
  className,
  children,
  id,
  ...rest
}: React.HTMLAttributes<HTMLElement> & { id?: string }) {
  return (
    <section
      id={id}
      className={cn("relative py-24 md:py-32", className)}
      {...rest}
    >
      {children}
    </section>
  );
}

type SectionHeadingProps = {
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  className?: React.HTMLAttributes<HTMLDivElement>["className"];
  tone?: "dark" | "light";
  align?: "left" | "center";
};

export function SectionHeading({
  eyebrow,
  title,
  description,
  className,
  tone = "dark",
  align = "left",
}: SectionHeadingProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4",
        align === "center" && "items-center text-center",
        className,
      )}
    >
      {eyebrow ? (
        <p
          className={cn(
            "text-subheading-md uppercase",
            tone === "dark" ? "text-text-sub-600" : "text-panel-text-sub",
          )}
        >
          {eyebrow}
        </p>
      ) : null}
      <h2
        className={cn(
          "text-display-sm font-serif",
          tone === "dark" ? "text-text-strong-950" : "text-panel-text",
        )}
      >
        {title}
      </h2>
      {description ? (
        <p
          className={cn(
            "max-w-2xl text-paragraph-lg",
            tone === "dark" ? "text-text-sub-600" : "text-panel-text-sub",
          )}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
