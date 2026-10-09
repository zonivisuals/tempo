"use client";

import * as React from "react";
import Image from "next/image";
import { motion, useReducedMotion } from "motion/react";
import { RiArrowRightLine, RiGridFill, RiListUnordered } from "@remixicon/react";

import { cn } from "@/utils/cn";
import { Logo } from "@/components/ui/logo";
import {
  markerTimecode,
  type QueryScenario,
} from "@/content/product";

type Stage = "idle" | "typing" | "results";

const TYPE_MS = 42;
const HOLD_MS = 3400;
const RESET_MS = 700;

/**
 * The Tempo panel as seen in the product: dark surface, one query, ranked
 * shot tiles. Success states only — the query always resolves.
 */
export function SearchPanel({
  scenario,
  className,
  showMarker = false,
  compact = false,
}: {
  scenario: QueryScenario;
  className?: string;
  showMarker?: boolean;
  compact?: boolean;
}) {
  const reduce = useReducedMotion();
  const [stage, setStage] = React.useState<Stage>("idle");
  const [typed, setTyped] = React.useState("");

  const query = scenario.query;
  const effectiveStage: Stage = reduce ? "results" : stage;
  const effectiveTyped = reduce ? query : typed;

  React.useEffect(() => {
    if (reduce) return;
    let charTimer: ReturnType<typeof setInterval> | undefined;
    let phaseTimer: ReturnType<typeof setTimeout> | undefined;

    if (stage === "idle") {
      phaseTimer = setTimeout(() => setStage("typing"), 900);
    } else if (stage === "typing") {
      let i = 0;
      charTimer = setInterval(() => {
        i += 1;
        setTyped(query.slice(0, i));
        if (i >= query.length) {
          if (charTimer) clearInterval(charTimer);
          phaseTimer = setTimeout(() => setStage("results"), 220);
        }
      }, TYPE_MS);
    } else {
      phaseTimer = setTimeout(() => {
        setStage("idle");
        setTyped("");
      }, HOLD_MS + RESET_MS);
    }

    return () => {
      if (charTimer) clearInterval(charTimer);
      if (phaseTimer) clearTimeout(phaseTimer);
    };
  }, [stage, query, reduce]);

  const showResults = effectiveStage === "results";
  const showGrid = showResults;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-12 bg-panel ring-1 ring-panel-stroke/80",
        className,
      )}
    >
      {/* Panel chrome */}
      <div className="flex items-center justify-between border-b border-panel-stroke px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
            <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
            <span className="size-2.5 rounded-full bg-[#4A4A4A]" />
          </div>
          <Logo tone="light" className="text-[13px]" />
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-panel-text-sub">
          {scenario.id === "ocean" ? "Wave_Study" : "City_Aerials"}
        </span>
      </div>

      {/* Search bar */}
      <div className="px-4 pt-4">
        <div className="flex items-center gap-3 rounded-10 bg-panel-raised px-3.5 py-2.5 ring-1 ring-panel-stroke">
          <input
            readOnly
            aria-label="Search query preview"
            placeholder="Search for anything"
            value={effectiveTyped}
            className="w-full bg-transparent text-paragraph-sm text-panel-text outline-none placeholder:text-panel-text-sub"
          />
          {effectiveStage === "typing" ? (
            <span className="size-2 shrink-0 animate-caret rounded-full bg-accent" aria-hidden="true" />
          ) : null}
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-full transition-colors duration-300",
              showResults ? "bg-accent text-white" : "bg-[#3A3A3A] text-panel-text-sub",
            )}
            aria-hidden="true"
          >
            <RiArrowRightLine className="size-3.5" />
          </span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2" aria-hidden="true">
          <span className="flex size-7 items-center justify-center rounded-md bg-panel-raised text-panel-text">
            <RiGridFill className="size-3.5" />
          </span>
          <span className="flex size-7 items-center justify-center rounded-md text-panel-text-sub">
            <RiListUnordered className="size-3.5" />
          </span>
        </div>
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-[0.14em] text-panel-text-sub transition-opacity duration-300",
            showResults ? "opacity-100" : "opacity-0",
          )}
        >
          {scenario.tiles.length} shots · ranked by match
        </span>
      </div>

      {/* Shot grid */}
      <div
        className={cn(
          "grid grid-cols-3 gap-2 px-4 pb-4",
          compact ? "gap-2" : "gap-3",
          showGrid ? "" : "hidden",
        )}
      >
        {scenario.tiles.map((tile, index) => (
          <motion.div
            key={tile.id}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={showResults ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
            transition={{
              duration: 0.45,
              delay: reduce ? 0 : index * 0.08,
              ease: [0.16, 1, 0.3, 1],
            }}
            className={cn(
              "group overflow-hidden rounded-8 bg-panel-surface ring-1 transition-[box-shadow] duration-200",
              index === 0 ? "ring-2 ring-accent" : "ring-panel-stroke",
            )}
          >
            <div className="relative aspect-video overflow-hidden">
              <Image
                src={tile.src}
                alt={tile.caption}
                width={480}
                height={300}
                sizes="(max-width: 1024px) 45vw, 240px"
                className="size-full object-cover saturate-[0.82] brightness-[0.92]"
              />
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-panel/60 to-transparent" />
            </div>
            <div className="flex flex-col gap-0.5 px-2.5 py-2">
              <span className="line-clamp-2 h-[2.2em] overflow-hidden text-[11px] leading-snug text-panel-text">
                {tile.caption}
              </span>
              <span className="font-mono text-[10px] text-panel-text-sub">
                {tile.duration}
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Marker strip */}
      {showMarker ? (
        <div
          className={cn(
            "flex items-center gap-3 border-t border-panel-stroke px-4 py-3 transition-opacity duration-500",
            showResults ? "opacity-100" : "opacity-0",
          )}
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-panel-text-sub">
            Timeline
          </span>
          <div className="relative h-1.5 flex-1 rounded-full bg-[#3A3A3A]">
            <span className="absolute left-[38%] top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-4 ring-accent/20" />
          </div>
          <span className="font-mono text-[11px] text-panel-text">{markerTimecode}</span>
        </div>
      ) : null}
    </div>
  );
}
