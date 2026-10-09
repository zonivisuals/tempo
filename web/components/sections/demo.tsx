"use client";

import * as React from "react";
import Image from "next/image";
import { motion, useInView, useReducedMotion } from "motion/react";
import { RiPauseFill, RiPlayFill } from "@remixicon/react";

import { cn } from "@/utils/cn";
import { demo } from "@/content/copy";
import { markerTimecode, projectName, scenarios } from "@/content/product";
import { Logo } from "@/components/ui/logo";

type Step = "typing" | "results" | "marker";

const CYCLE_MS = 9600;
const BOUNDARIES = [0.22, 0.5, 0.74]; // typing -> results -> marker -> hold

function stepForProgress(p: number): Step {
  if (p < BOUNDARIES[0]) return "typing";
  if (p < BOUNDARIES[1]) return "results";
  return "marker";
}

export function DemoReel() {
  const reduce = useReducedMotion();
  const sectionRef = React.useRef<HTMLElement>(null);
  const inView = useInView(sectionRef, { margin: "-20% 0px" });

  const [playing, setPlaying] = React.useState(true);
  const [progress, setProgress] = React.useState(0);
  const query = scenarios[0];
  const activeStep: Step = reduce ? "marker" : stepForProgress(progress);
  const localTyping = Math.floor((progress / BOUNDARIES[0]) * query.query.length);
  const queryText = reduce
    ? query.query
    : progress < BOUNDARIES[0]
      ? query.query.slice(0, localTyping)
      : query.query;

  // Timeline driver — resumes from progressRef so pausing keeps place
  const progressRef = React.useRef(0);
  React.useEffect(() => {
    progressRef.current = progress;
  }, [progress]);
  React.useEffect(() => {
    if (reduce) return;
    if (!inView || !playing) return;
    let raf = 0;
    const start = performance.now() - progressRef.current * CYCLE_MS;
    const tick = (now: number) => {
      const p = ((now - start) % CYCLE_MS) / CYCLE_MS;
      setProgress(p);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, playing, reduce]);

  const tiles = query.tiles.slice(0, 6);
  const featured = tiles[0];

  return (
    <section
      id="demo"
      ref={sectionRef}
      className="relative bg-panel py-24 text-panel-text md:py-32"
    >
      <div className="mx-auto w-full max-w-6xl px-6">
        <div className="flex flex-col items-start gap-4">
          <p className="text-subheading-md uppercase text-panel-text-sub">
            {demo.eyebrow}
          </p>
          <h2 className="text-display-sm font-serif text-panel-text">
            {demo.title}
          </h2>
          <p className="max-w-2xl text-paragraph-lg text-panel-text-sub">
            {demo.description}
          </p>
        </div>

        {/* Faux editor window */}
        <div className="mt-14 overflow-hidden rounded-12 bg-panel-surface ring-1 ring-panel-stroke shadow-[0_40px_120px_rgba(0,0,0,0.35)]">
          {/* Window chrome */}
          <div className="flex items-center justify-between border-b border-panel-stroke px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5" aria-hidden="true">
                <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
                <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
                <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
              </div>
              <span className="font-mono text-[11px] text-panel-text-sub">
                {projectName}
              </span>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-panel-text-sub">
              After Effects
            </span>
          </div>

          <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-[1.1fr_1fr]">
            {/* Tempo panel */}
            <div className="flex flex-col rounded-10 bg-panel p-4 ring-1 ring-panel-stroke">
              <div className="flex items-center justify-between pb-4">
                <Logo tone="light" className="text-[12px]" />
                <span
                  className={cn(
                    "font-mono text-[10px] uppercase tracking-[0.14em] transition-opacity duration-300",
                    activeStep === "typing"
                      ? "text-panel-text-sub opacity-100"
                      : "opacity-0",
                  )}
                >
                  searching
                </span>
              </div>

              <div className="flex items-center gap-3 rounded-10 bg-panel-raised px-3.5 py-2.5 ring-1 ring-panel-stroke">
                <input
                  readOnly
                  aria-label="Demo search query"
                  placeholder="Search for anything"
                  value={queryText}
                  className="w-full bg-transparent text-paragraph-sm text-panel-text outline-none placeholder:text-panel-text-sub"
                />
                {activeStep === "typing" && !reduce ? (
                  <span className="size-2 shrink-0 animate-caret rounded-full bg-accent" aria-hidden="true" />
                ) : null}
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full transition-colors duration-300",
                    activeStep === "typing"
                      ? "bg-[#3A3A3A] text-panel-text-sub"
                      : "bg-accent text-white",
                  )}
                  aria-hidden="true"
                >
                  <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />
                  </svg>
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-4">
                {tiles.map((tile, index) => (
                  <motion.div
                    key={tile.id}
                    initial={reduce ? false : { opacity: 0, y: 10 }}
                    animate={
                      activeStep === "typing"
                        ? { opacity: 0, y: 10 }
                        : { opacity: 1, y: 0 }
                    }
                    transition={{
                      duration: 0.4,
                      delay: reduce ? 0 : index * 0.07,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                    className={cn(
                      "overflow-hidden rounded-8 bg-panel-surface ring-1 transition-[box-shadow]",
                      index === 0 && activeStep === "marker"
                        ? "ring-2 ring-accent"
                        : "ring-panel-stroke",
                    )}
                  >
                    <div className="relative aspect-video overflow-hidden">
                      <Image
                        src={tile.src}
                        alt={tile.caption}
                        width={480}
                        height={300}
                        sizes="(max-width: 1024px) 30vw, 180px"
                        className="size-full object-cover saturate-[0.82] brightness-[0.92]"
                      />
                      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-panel/60 to-transparent" />
                    </div>
                    <div className="flex flex-col gap-0.5 px-2 py-1.5">
                      <span className="truncate text-[10px] text-panel-text">
                        {tile.caption}
                      </span>
                      <span className="font-mono text-[9px] text-panel-text-sub">
                        {tile.duration}
                      </span>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* Composition view */}
            <div className="flex flex-col rounded-10 bg-panel p-4 ring-1 ring-panel-stroke">
              <div className="flex items-center justify-between pb-3">
                <span className="text-subheading-2xs uppercase text-panel-text-sub">
                  Composition
                </span>
                <span
                  className={cn(
                    "font-mono text-[11px] transition-colors duration-300",
                    activeStep === "marker" ? "text-accent" : "text-panel-text-sub",
                  )}
                >
                  {activeStep === "marker" ? markerTimecode : "00:00:00:00"}
                </span>
              </div>

              <div className="relative flex-1 overflow-hidden rounded-8 bg-[#1C1C1C] ring-1 ring-panel-stroke">
                <motion.div
                  className="absolute inset-0"
                  initial={false}
                  animate={{ opacity: activeStep === "typing" ? 0 : 1 }}
                  transition={{ duration: 0.4 }}
                >
                  <Image
                    src={featured.src}
                    alt={featured.caption}
                    fill
                    sizes="(max-width: 1024px) 90vw, 420px"
                    className="object-cover saturate-[0.82] brightness-[0.92]"
                  />
                </motion.div>
                {activeStep === "typing" ? (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-panel-text-sub">
                      waiting for query
                    </span>
                  </div>
                ) : null}
                {activeStep === "marker" ? (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    className="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-accent px-3 py-1"
                  >
                    <span className="size-1.5 rounded-full bg-white" aria-hidden="true" />
                    <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-white">
                      Marker · {featured.caption}
                    </span>
                  </motion.div>
                ) : null}
              </div>

              {/* Scrub bar */}
              <div className="relative mt-4 h-1.5 rounded-full bg-[#3A3A3A]">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full bg-accent/40"
                  initial={false}
                  animate={{ width: activeStep === "marker" ? "38%" : "0%" }}
                  transition={{ duration: activeStep === "marker" ? 1.6 : 0.3, ease: [0.16, 1, 0.3, 1] }}
                />
                <motion.div
                  className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-4 ring-accent/20"
                  initial={false}
                  animate={{ left: activeStep === "marker" ? "38%" : "0%" }}
                  transition={{ duration: activeStep === "marker" ? 1.6 : 0.3, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? demo.controls.pause : demo.controls.play}
              className="flex size-10 items-center justify-center rounded-full border border-panel-stroke text-panel-text transition-colors duration-200 hover:bg-panel-raised"
            >
              {playing ? (
                <RiPauseFill className="size-4" aria-hidden="true" />
              ) : (
                <RiPlayFill className="size-4" aria-hidden="true" />
              )}
            </button>
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-panel-text-sub">
              {activeStep === "typing"
                ? demo.steps[0].label
                : activeStep === "results"
                  ? demo.steps[1].label
                  : demo.steps[2].label}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="h-1 w-40 overflow-hidden rounded-full bg-[#3A3A3A]">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${progress * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
