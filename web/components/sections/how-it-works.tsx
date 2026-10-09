import Image from "next/image";

import { howItWorks } from "@/content/copy";
import { scenarios } from "@/content/product";
import { markerTimecode } from "@/content/product";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section";
import { Logo } from "@/components/ui/logo";

const clips = [
  { name: "A001_B-alpha_070512.mov", dur: "0:38" },
  { name: "C014_drone_city_sunset.mov", dur: "1:12" },
  { name: "B007_rooftop_descent.mov", dur: "0:24" },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-24 md:py-32">
      <div className="mx-auto w-full max-w-5xl px-6">
        <Reveal>
          <SectionHeading
            eyebrow={howItWorks.eyebrow}
            title={howItWorks.title}
          />
        </Reveal>

        <div className="mt-16 flex flex-col gap-4">
          {howItWorks.steps.map((step, index) => (
            <Reveal key={step.number} delay={index * 0.08}>
              <div className="grid grid-cols-1 items-center gap-8 rounded-12 border border-stroke-soft-200 bg-bg-white-0 p-8 md:grid-cols-[1fr_1.1fr] md:p-10">
                <div className="flex flex-col gap-4">
                  <span className="font-mono text-label-lg text-text-sub-600">
                    {step.number}
                  </span>
                  <h3 className="text-title-h4 text-text-strong-950">
                    {step.title}
                  </h3>
                  <p className="max-w-md text-paragraph-md text-text-sub-600">
                    {step.body}
                  </p>
                </div>

                {index === 0 ? (
                  <div className="overflow-hidden rounded-10 bg-panel p-4 ring-1 ring-panel-stroke">
                    <div className="flex items-center justify-between pb-3">
                      <Logo tone="light" className="text-[11px]" />
                      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-panel-text-sub">
                        3 clips ready
                      </span>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {clips.map((clip) => (
                        <div
                          key={clip.name}
                          className="flex items-center gap-3 rounded-md bg-panel-surface px-3 py-2"
                        >
                          <span className="size-3.5 shrink-0 rounded-sm bg-accent" aria-hidden="true" />
                          <span className="flex-1 truncate font-mono text-[11px] text-panel-text">
                            {clip.name}
                          </span>
                          <span className="font-mono text-[10px] text-panel-text-sub">
                            {clip.dur}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {index === 1 ? (
                  <div className="flex flex-col gap-3 rounded-10 bg-panel p-4 ring-1 ring-panel-stroke">
                    <div className="flex items-center gap-3 rounded-8 bg-panel-raised px-3.5 py-2.5 ring-1 ring-panel-stroke">
                      <span className="flex-1 text-paragraph-sm text-panel-text">
                        {scenarios[0].query}
                      </span>
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-white" aria-hidden="true">
                        <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                          <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />
                        </svg>
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {["drone shot", "city", "sunset"].map((chip) => (
                        <span
                          key={chip}
                          className="rounded-full bg-panel-surface px-2.5 py-1 text-[10px] uppercase tracking-[0.08em] text-panel-text-sub"
                        >
                          {chip}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {index === 2 ? (
                  <div className="flex items-center gap-3 rounded-10 bg-panel p-4 ring-1 ring-panel-stroke">
                    <div className="relative size-16 shrink-0 overflow-hidden rounded-8 ring-2 ring-accent">
                      <Image
                        src="/frames/skyline-a.jpg"
                        alt=""
                        width={128}
                        height={128}
                        sizes="64px"
                        className="size-full object-cover saturate-[0.82] brightness-[0.92]"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-label-md text-panel-text">
                        {scenarios[0].tiles[0].caption}
                      </span>
                      <span className="font-mono text-[11px] text-accent">
                        {markerTimecode} · marker added
                      </span>
                    </div>
                  </div>
                ) : null}
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

