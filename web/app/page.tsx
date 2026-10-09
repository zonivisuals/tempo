import { AmbientLayers } from "@/components/ambient";
import { Audience } from "@/components/sections/audience";
import { Comparison } from "@/components/sections/comparison";
import { Hero } from "@/components/hero";
import { Problem } from "@/components/sections/problem";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";

export default function Home() {
  return (
    <>
      <AmbientLayers />
      <SiteNav />
      <main className="relative z-1">
        <Hero />
        <Audience />
        <Problem />
        <Comparison />
      </main>
      <div className="relative z-1">
        <SiteFooter />
      </div>
    </>
  );
}
