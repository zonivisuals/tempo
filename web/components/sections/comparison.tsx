"use client";

import * as React from "react";
import Image from "next/image";
import { motion, useInView, useReducedMotion } from "motion/react";
import { RiArrowRightLine, RiLoader4Line } from "@remixicon/react";

import { cn } from "@/utils/cn";
import { comparison } from "@/content/copy";
import { markerTimecode, scenarios } from "@/content/product";
import { Logo } from "@/components/ui/logo";
import { SectionHeading } from "@/components/section";
import { Reveal } from "@/components/reveal";

const MANUAL_STEP_MS = 1100;
const MANUAL_TOTAL_S = 107 * 60 + 32;

function formatClock(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h, m, sec].map((n) => String(n).padStart(2, "0")).join(":");
}

function useCountdown(active: boolean, to: number, reduce: boolean) {
  const animate = active && !reduce;
  const [value, setValue] = React.useState(0);
  React.useEffect(() => {
    if (!animate) return;
    let raf = 0;
    const start = performance.now();
    const duration = 4800;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(to * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [animate, to]);
  return animate ? value : to;
}

export function Comparison() {
  const reduce = useReducedMotion();
  const sectionRef = React.useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { once: true, margin: "-15% 0px" });
  const active = inView;

  const [revealed, setRevealed] = React.useState(0);
  const query = scenarios[0];
  const [typed, setTyped] = React.useState("");
  const [tempoDone, setTempoDone] = React.useState(false);

  const manualClock = useCountdown(active, MANUAL_TOTAL_S, !!reduce);
  const tempoClock = useCountdown(active, 9, !!reduce);

  const revealedCount = reduce ? comparison.manual.steps.length : revealed;
  const queryText = reduce ? query.query : typed;
  const tempoFinished = reduce || tempoDone;

  React.useEffect(() => {
    if (!active || reduce) return;
    const timers = comparison.manual.steps.map((_, index) =>
      setTimeout(() => setRevealed(index + 1), 500 + index * MANUAL_STEP_MS),
    );
    return () => timers.forEach(clearTimeout);
  }, [active, reduce]);

  React.useEffect(() => {
    if (!active || reduce) return;
    let i = 0;
    const timer = setInterval(() => {
      i += 1;
      setTyped(query.query.slice(0, i));
      if (i >= query.query.length) {
        clearInterval(timer);
        setTimeout(() => setTempoDone(true), 260);
      }
    }, 34);
    return () => clearInterval(timer);
  }, [active, reduce, query.query]);

  return (
    <section className="relative py-24 md:py-32" ref={sectionRef} id="compare">
      <div className="mx-auto w-full max-w-5xl px-6">
        <Reveal>
          <SectionHeading
            eyebrow={comparison.eyebrow}
            title={comparison.title}
          />
        </Reveal>

        <div className="mt-16 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Manual */}
          <Reveal delay={0.05}>
            <div className="flex h-full flex-col rounded-12 border border-stroke-soft-200 bg-bg-white-0 p-8">
              <div className="flex items-center justify-between">
                <span className="text-subheading-md uppercase text-text-sub-600">
                  {comparison.manual.label}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-label-sm text-text-sub-600">
                  <RiLoader4Line
                    className={cn("size-3.5", active && !reduce && "animate-spin")}
                    aria-hidden="true"
                  />
                  {comparison.manual.elapsedLabel}
                </span>
              </div>

              <div className="mt-6 font-mono text-title-h3 tabular-nums text-text-strong-950">
                {formatClock(manualClock)}
              </div>

              <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-bg-soft-200">
                <div
                  className="h-full rounded-full bg-neutral-400 transition-[width] duration-200 ease-linear"
                  style={{
                    width: `${Math.min(100, (manualClock / MANUAL_TOTAL_S) * 100)}%`,
                  }}
                />
              </div>

              <ul className="mt-8 flex flex-col gap-4">
                {comparison.manual.steps.map((step, index) => {
                  const shown = index < revealedCount;
                  return (
                    <li
                      key={step}
                      className={cn(
                        "flex items-center gap-3 transition-all duration-500 ease-out",
                        shown
                          ? "translate-y-0 opacity-100"
                          : "translate-y-1.5 opacity-0",
                      )}
                    >
                      <span className="font-mono text-label-sm text-text-soft-400">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="text-paragraph-sm text-text-sub-600">
                        {step}
                      </span>
                    </li>
                  );
                })}
              </ul>

              <p className="mt-8 border-t border-stroke-soft-200 pt-6 text-paragraph-xs text-text-soft-400">
                Still looking.
              </p>
            </div>
          </Reveal>

          {/* Tempo */}
          <Reveal delay={0.12}>
            <div className="flex h-full flex-col rounded-12 bg-panel p-8 ring-1 ring-panel-stroke">
              <div className="flex items-center justify-between">
                <span className="text-subheading-md uppercase text-panel-text-sub">
                  {comparison.tempo.label}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-label-sm text-panel-text-sub">
                  <RiArrowRightLine className="size-3.5 text-accent" aria-hidden="true" />
                  {comparison.tempo.elapsedLabel}
                </span>
              </div>

              <div className="mt-6 flex items-baseline gap-3">
                <span className="font-mono text-title-h3 tabular-nums text-panel-text">
                  {tempoFinished ? "00:00:09" : formatClock(tempoClock)}
                </span>
                <span
                  className={cn(
                    "rounded-full px-2.5 py-1 text-subheading-2xs uppercase transition-opacity duration-300",
                    tempoFinished ? "bg-accent text-white opacity-100"
                      : "bg-panel-raised text-panel-text-sub opacity-0",
                  )}
                >
                  Found
                </span>
              </div>

              <div className="mt-6 flex items-center gap-3 rounded-10 bg-panel-raised px-3.5 py-2.5 ring-1 ring-panel-stroke">
                <input
                  readOnly
                  aria-label="Tempo query preview"
                  placeholder="Search for anything"
                  value={queryText}
                  className="w-full bg-transparent text-paragraph-sm text-panel-text outline-none placeholder:text-panel-text-sub"
                />
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full transition-colors duration-300",
                    tempoFinished ? "bg-accent text-white" : "bg-[#3A3A3A] text-panel-text-sub",
                  )}
                  aria-hidden="true"
                >
                  <RiArrowRightLine className="size-3.5" />
                </span>
              </div>

              <div className="mt-5 flex flex-col gap-2">
                {query.tiles.slice(0, 3).map((tile, index) => (
                  <motion.div
                    key={tile.id}
                    initial={reduce ? false : { opacity: 0, y: 8 }}
                    animate={tempoFinished ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
                    transition={{ duration: 0.4, delay: reduce ? 0 : index * 0.08, ease: [0.16, 1, 0.3, 1] }}
                    className={cn(
                      "flex items-center gap-3 rounded-8 bg-panel-surface p-2 ring-1",
                      index === 0 ? "ring-accent" : "ring-panel-stroke",
                    )}
                  >
                    <div className="relative size-11 shrink-0 overflow-hidden rounded-6">
                      <Image
                        src={tile.src}
                        alt=""
                        width={96}
                        height={96}
                        className="size-full object-cover saturate-[0.82] brightness-[0.92]"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] text-panel-text">{tile.caption}</p>
                      <p className="font-mono text-[10px] text-panel-text-sub">{tile.duration}</p>
                    </div>
                    {index === 0 ? (
                      <span className="font-mono text-[10px] text-accent">{markerTimecode}</span>
                    ) : null}
                  </motion.div>
                ))}
              </div>

              <p className="mt-8 border-t border-panel-stroke pt-6 text-paragraph-xs text-panel-text-sub">
                Shot in the timeline, marker placed.
              </p>
            </div>
          </Reveal>
        </div>

        <Reveal delay={0.2}>
          <div className="mt-10 flex items-center justify-center gap-3 text-paragraph-sm text-text-sub-600">
            <Logo className="text-[11px]" />
            <span className="text-text-soft-400">·</span>
            <span>Same project. Same footage. Different afternoon.</span>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

