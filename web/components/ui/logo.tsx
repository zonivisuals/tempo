import { cn } from "@/utils/cn";

type LogoProps = {
  className?: string;
  tone?: "dark" | "light";
};

export function Logo({ className, tone = "dark" }: LogoProps) {
  return (
    <span
      className={cn(
        "select-none font-sans text-title-h6 font-semibold uppercase tracking-[0.24em]",
        tone === "dark" ? "text-text-strong-950" : "text-panel-text",
        className,
      )}
    >
      <span className="text-accent">T</span>EMPO
    </span>
  );
}
