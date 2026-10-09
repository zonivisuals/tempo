import { footer, site } from "@/content/copy";
import { Logo } from "@/components/ui/logo";
import { Container } from "@/components/section";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-stroke-soft-200">
      <Container className="flex flex-col gap-8 py-12 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-2">
          <Logo className="w-fit" />
          <p className="text-paragraph-sm text-text-sub-600">
            {footer.note} © {site.year} {site.name}.
          </p>
        </div>
        <nav aria-label="Footer" className="flex items-center gap-6">
          {footer.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-label-md text-text-sub-600 transition-colors hover:text-text-strong-950"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </Container>
    </footer>
  );
}
