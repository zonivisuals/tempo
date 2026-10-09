import { AmbientLayers } from "@/components/ambient";
import { Hero } from "@/components/hero";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";

export default function Home() {
  return (
    <>
      <AmbientLayers />
      <SiteNav />
      <main className="relative z-1">
        <Hero />
      </main>
      <div className="relative z-1">
        <SiteFooter />
      </div>
    </>
  );
}
