import * as Button from "@/components/ui/button";
import * as Input from "@/components/ui/input";
import { Tag } from "@/components/ui/tag";
import { Kbd } from "@/components/ui/kbd";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Logo } from "@/components/ui/logo";
import { AmbientLayers } from "@/components/ambient";
import { Reveal } from "@/components/reveal";
import { Section } from "@/components/section";
import { RiArrowRightSLine, RiSearchLine } from "@remixicon/react";

export default function Home() {
  return (
    <>
      <AmbientLayers />
      <main className="relative z-1">
        <Section className="space-y-12">
          <div className="flex flex-wrap items-center gap-4">
            <Logo />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button.Root variant="neutral" mode="filled">
              Get early access
              <Button.Icon as={RiArrowRightSLine} />
            </Button.Root>
            <Button.Root variant="primary" mode="filled">
              Watch demo
            </Button.Root>
            <Button.Root variant="neutral" mode="stroke">
              Stroke
            </Button.Root>
            <Button.Root variant="neutral" mode="ghost">
              Ghost
            </Button.Root>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Tag tone="orange">After Effects</Tag>
            <Tag tone="blue">Premiere Pro</Tag>
            <Tag tone="green">DaVinci Resolve</Tag>
            <Tag tone="yellow">Coming soon</Tag>
            <Tag tone="neutral">CLIP + Whisper</Tag>
          </div>

          <div className="max-w-md">
            <Input.Root>
              <Input.Wrapper>
                <Input.Icon as={RiSearchLine} />
                <Input.Input placeholder="Search for anything" />
              </Input.Wrapper>
            </Input.Root>
          </div>

          <div className="flex items-center gap-3">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
            <span className="text-paragraph-sm text-text-sub-600">to search</span>
          </div>

          <div className="max-w-md space-y-2">
            <ProgressBar value={64} />
          </div>

          <Accordion type="single" collapsible className="max-w-2xl">
            <AccordionItem value="a">
              <AccordionTrigger>What is Tempo?</AccordionTrigger>
              <AccordionContent>
                A semantic search plugin for video editors. Describe a shot in plain words and jump to it.
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="b">
              <AccordionTrigger>Which apps are supported?</AccordionTrigger>
              <AccordionContent>
                After Effects at launch, with Premiere Pro and DaVinci Resolve on the roadmap.
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <Reveal>
            <p className="text-title-h4 font-serif">Reveal works.</p>
          </Reveal>
        </Section>
      </main>
    </>
  );
}
