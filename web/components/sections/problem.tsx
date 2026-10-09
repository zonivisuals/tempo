import {
  RiFileList2Line,
  RiEyeLine,
  RiPriceTag3Line,
  RiTimeLine,
} from "@remixicon/react";

import { problem } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section";

const icons = [RiFileList2Line, RiEyeLine, RiPriceTag3Line, RiTimeLine];
const spans = ["md:col-span-4", "md:col-span-2", "md:col-span-2", "md:col-span-4"];

export function Problem() {
  return (
    <section id="problem" className="relative py-24 md:py-32">
      <div className="mx-auto w-full max-w-5xl px-6">
        <Reveal>
          <SectionHeading
            eyebrow={problem.eyebrow}
            title={problem.title}
            description={problem.description}
          />
        </Reveal>

        <div className="mt-16 grid grid-cols-1 gap-4 md:grid-cols-6">
          {problem.cards.map((card, index) => {
            const Icon = icons[index] ?? RiFileList2Line;
            return (
              <Reveal
                key={card.title}
                delay={index * 0.08}
                className={spans[index]}
              >
                <div className="group flex h-full flex-col gap-4 rounded-12 border border-stroke-soft-200 bg-bg-white-0 p-8 transition-shadow duration-200 hover:shadow-soft">
                  <div className="flex items-start justify-between">
                    <span className="flex size-10 items-center justify-center rounded-10 bg-bg-soft-200 text-text-strong-950 transition-colors duration-200 group-hover:bg-primary-alpha-10 group-hover:text-primary-base">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <span className="font-mono text-label-sm text-text-sub-600">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <h3 className="text-title-h6 text-text-strong-950">
                    {card.title}
                  </h3>
                  <p className="max-w-md text-paragraph-sm text-text-sub-600">
                    {card.body}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}

