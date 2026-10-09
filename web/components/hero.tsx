import { RiPlayCircleLine } from "@remixicon/react";

import { hero } from "@/content/copy";
import { scenarios } from "@/content/product";
import { SearchPanel } from "@/components/product/search-panel";
import { Reveal } from "@/components/reveal";
import { Tag } from "@/components/ui/tag";
import { WaitlistForm } from "@/components/waitlist-form";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="relative z-1 mx-auto grid w-full max-w-6xl items-center gap-16 px-6 pb-24 pt-20 lg:grid-cols-[1.05fr_1fr] lg:gap-12 lg:pb-32 lg:pt-28">
        <div className="flex flex-col items-start">
          <Reveal>
            <Tag tone="orange" className="mb-6 gap-1.5">
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              {hero.eyebrow}
            </Tag>
          </Reveal>

          <Reveal delay={0.06}>
            <h1 className="max-w-xl text-display font-serif text-text-strong-950">
              {hero.title}
            </h1>
          </Reveal>

          <Reveal delay={0.12}>
            <p className="mt-6 max-w-md text-paragraph-lg text-text-sub-600">
              {hero.description}
            </p>
          </Reveal>

          <Reveal delay={0.18} className="mt-9 w-full max-w-lg">
            <div id="waitlist">
              <WaitlistForm
                placeholder={hero.form.placeholder}
                ctaLabel={hero.form.cta}
              />
            </div>
            <p className="mt-3 text-paragraph-xs text-text-sub-600">
              {hero.form.note}
            </p>
          </Reveal>

          <Reveal delay={0.24}>
            <a
              href={hero.demoLink.href}
              className="group mt-8 inline-flex items-center gap-2 text-label-md text-text-sub-600 transition-colors hover:text-text-strong-950"
            >
              <RiPlayCircleLine
                className="size-5 text-accent transition-transform duration-200 group-hover:scale-105"
                aria-hidden="true"
              />
              {hero.demoLink.label}
            </a>
          </Reveal>
        </div>

        <Reveal delay={0.1} className="w-full">
          <div className="relative">
            <div
              aria-hidden="true"
              className="absolute -inset-6 -z-1 rounded-[28px] bg-[radial-gradient(60%_60%_at_70%_30%,rgba(235,80,23,0.07),transparent_70%)]"
            />
            <SearchPanel
              scenario={scenarios[0]}
              className="shadow-panel lg:[transform:perspective(1400px)_rotateY(-1.5deg)_rotateX(0.75deg)]"
            />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

