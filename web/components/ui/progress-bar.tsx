import { cn } from "@/utils/cn";

type ProgressBarProps = {
  value: number;
  className?: string;
  barClassName?: string;
};

export function ProgressBar({ value, className, barClassName }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-bg-soft-200",
        className,
      )}
    >
      <div
        className={cn("h-full rounded-full bg-accent transition-[width] duration-200 ease-out", barClassName)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
