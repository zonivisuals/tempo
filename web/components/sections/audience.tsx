import { audience } from "@/content/copy";
import { Reveal } from "@/components/reveal";
import { Tag } from "@/components/ui/tag";
import { Container, Section } from "@/components/section";

const tones = ["orange", "blue", "green", "yellow", "neutral"] as const;

export function Audience() {
  return (
    <Section className="py-16">
      <Container>
        <div className="flex flex-col items-start gap-8 md:flex-row md:items-center md:justify-between">
          <Reveal>
            <p className="max-w-xs text-label-lg text-text-strong-950">
              {audience.title}
            </p>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="flex flex-wrap gap-2">
              {audience.roles.map((role, index) => (
                <Tag key={role} tone={tones[index % tones.length]}>
                  {role}
                </Tag>
              ))}
            </div>
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
