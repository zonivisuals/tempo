import { Audience } from "@/components/sections/audience";
import { Hero } from "@/components/hero";
import { Problem } from "@/components/sections/problem";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";
import { AmbientLayers } from "@/components/ambient";

export default function Home() {
  return (
    <>
      <AmbientLayers />
      <SiteNav />
      <main className="relative z-1">
        <Hero />
        <Audience />
        <Problem />
      </main>
      <div className="relative z-1">
        <SiteFooter />
      </div>
    </>
  );
}
