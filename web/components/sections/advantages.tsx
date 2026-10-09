import { advantages } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section";
import { Tag } from "@/components/ui/tag";

export function Advantages() {
  return (
    <section id="advantages" className="relative py-24 md:py-32">
      <div className="mx-auto w-full max-w-5xl px-6">
        <Reveal>
          <SectionHeading
            eyebrow={advantages.eyebrow}
            title={advantages.title}
          />
        </Reveal>

        <div className="mt-16 grid grid-cols-1 gap-4 md:grid-cols-6">
          {advantages.items.map((item, index) => (
            <Reveal
              key={item.title}
              delay={index * 0.08}
              className={index % 2 === 0 ? "md:col-span-4" : "md:col-span-2"}
            >
              <div className="flex h-full flex-col gap-4 rounded-12 border border-stroke-soft-200 bg-bg-white-0 p-8 transition-shadow duration-200 hover:shadow-soft md:p-10">
                <Tag tone={item.tone} className="w-fit">
                  {item.tag}
                </Tag>
                <h3 className="text-title-h5 text-text-strong-950">
                  {item.title}
                </h3>
                <p className="max-w-lg text-paragraph-md text-text-sub-600">
                  {item.body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
