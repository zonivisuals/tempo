import * as Button from "@/components/ui/button";
import { platforms } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section";
import { RiCheckLine, RiTimeLine } from "@remixicon/react";

export function Platforms() {
  return (
    <section id="platforms" className="relative py-24 md:py-32">
      <div className="mx-auto w-full max-w-5xl px-6">
        <Reveal>
          <SectionHeading eyebrow={platforms.eyebrow} title={platforms.title} />
        </Reveal>

        <div className="mt-16 grid grid-cols-1 gap-4 md:grid-cols-6">
          <Reveal delay={0.05} className="md:col-span-3">
            <div className="flex h-full flex-col gap-5 rounded-12 border border-stroke-strong-950 bg-bg-strong-950 p-8 md:p-10">
              <div className="flex items-center justify-between">
                <span className="font-sans text-title-h4 font-semibold uppercase tracking-[0.18em] text-panel-text">
                  {platforms.live.name}
                </span>
                <span className="flex items-center gap-1.5 rounded-full bg-tag-green-bg px-3 py-1 text-subheading-2xs uppercase text-tag-green-fg">
                  <RiCheckLine className="size-3" aria-hidden="true" />
                  {platforms.live.status}
                </span>
              </div>
              <p className="max-w-sm text-paragraph-md text-panel-text-sub">
                {platforms.live.detail}
              </p>
              <div className="mt-auto flex items-center gap-2 pt-4">
                <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
                <span className="text-paragraph-sm text-panel-text-sub">
                  {platforms.waitlistNote}
                </span>
              </div>
            </div>
          </Reveal>

          {platforms.roadmap.map((item, index) => (
            <Reveal key={item.name} delay={0.12 + index * 0.08} className="md:col-span-3">
              <div className="flex h-full flex-col gap-5 rounded-12 border border-stroke-soft-200 bg-bg-white-0 p-8 md:p-10">
                <div className="flex items-center justify-between">
                  <span className="font-sans text-title-h4 font-semibold uppercase tracking-[0.18em] text-text-strong-950">
                    {item.name}
                  </span>
                  <span className="flex items-center gap-1.5 rounded-full bg-tag-yellow-bg px-3 py-1 text-subheading-2xs uppercase text-tag-yellow-fg">
                    <RiTimeLine className="size-3" aria-hidden="true" />
                    Roadmap
                  </span>
                </div>
                <p className="max-w-sm text-paragraph-md text-text-sub-600">
                  {item.detail}
                </p>
                <div className="mt-auto pt-4">
                  <Button.Root asChild variant="neutral" mode="stroke" size="small">
                    <a href="#waitlist">Notify me</a>
                  </Button.Root>
                </div>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2}>
          <p className="mt-8 text-paragraph-sm text-text-sub-600">
            Waitlist members get each new platform first — in the order they
            signed up.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

