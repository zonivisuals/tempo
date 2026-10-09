import { finalCta, hero } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { WaitlistForm } from "@/components/waitlist-form";
import { Container, Section } from "@/components/section";

export function FinalCta() {
  return (
    <Section className="relative overflow-hidden py-28 md:py-36">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(36rem_24rem_at_50%_120%,rgba(235,80,23,0.06),transparent_70%)]"
      />
      <Container className="relative flex flex-col items-center text-center">
        <Reveal>
          <h2 className="max-w-2xl text-display font-serif text-text-strong-950">
            {finalCta.title}
          </h2>
        </Reveal>
        <Reveal delay={0.08}>
          <p className="mt-6 max-w-xl text-paragraph-lg text-text-sub-600">
            {finalCta.description}
          </p>
        </Reveal>
        <Reveal delay={0.16} className="mt-10 w-full max-w-lg">
          <WaitlistForm placeholder={hero.form.placeholder} ctaLabel={hero.form.cta} />
        </Reveal>
      </Container>
    </Section>
  );
}

