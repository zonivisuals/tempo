import { faq } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export function Faq() {
  return (
    <section id="faq" className="relative py-24 md:py-32">
      <div className="mx-auto w-full max-w-5xl px-6">
        <div className="grid grid-cols-1 gap-12 md:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <SectionHeading eyebrow={faq.eyebrow} title={faq.title} />
          </Reveal>

          <Reveal delay={0.1}>
            <Accordion type="single" collapsible className="w-full">
              {faq.items.map((item) => (
                <AccordionItem key={item.q} value={item.q}>
                  <AccordionTrigger>{item.q}</AccordionTrigger>
                  <AccordionContent>{item.a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
