import Link from "next/link";

import { nav } from "@/content/copy";
import * as Button from "@/components/ui/button";
import { Logo } from "@/components/ui/logo";
import { Container } from "@/components/section";

export function SiteNav() {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-60 focus:rounded-6 focus:bg-bg-strong-950 focus:px-4 focus:py-2 focus:text-label-sm focus:text-text-white-0"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-50 border-b border-stroke-soft-200/70 bg-bg-weak-50/80 backdrop-blur-md">
      <Container className="flex h-16 items-center justify-between gap-6">
        <Link href="/" aria-label="Tempo home" className="shrink-0">
          <Logo />
        </Link>

        <nav aria-label="Sections" className="hidden items-center gap-8 md:flex">
          {nav.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-label-md text-text-sub-600 transition-colors hover:text-text-strong-950"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <Button.Root asChild variant="neutral" mode="filled" size="xsmall">
          <a href={nav.cta.href}>{nav.cta.label}</a>
        </Button.Root>
      </Container>
      </header>
    </>
  );
}
