import { AmbientLayers } from "@/components/ambient";
import { WaitlistForm } from "@/components/waitlist-form";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";
import { hero } from "@/content/copy";

export default function Home() {
  return (
    <>
      <AmbientLayers />
      <SiteNav />
      <main className="relative z-1">
        <section className="mx-auto w-full max-w-5xl px-6 py-24">
          <p className="text-subheading-md uppercase text-text-sub-600">
            {hero.eyebrow}
          </p>
          <h1 className="mt-4 max-w-3xl text-display font-serif text-text-strong-950">
            {hero.title}
          </h1>
          <p className="mt-6 max-w-2xl text-paragraph-lg text-text-sub-600">
            {hero.description}
          </p>
          <div className="mt-10 max-w-lg" id="waitlist">
            <WaitlistForm placeholder={hero.form.placeholder} ctaLabel={hero.form.cta} />
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
