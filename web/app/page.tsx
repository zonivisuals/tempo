import { AmbientLayers } from "@/components/ambient";
import { Advantages } from "@/components/sections/advantages";
import { Audience } from "@/components/sections/audience";
import { Comparison } from "@/components/sections/comparison";
import { Faq } from "@/components/sections/faq";
import { Hero } from "@/components/hero";
import { HowItWorks } from "@/components/sections/how-it-works";
import { Platforms } from "@/components/sections/platforms";
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
        <HowItWorks />
        <Advantages />
        <Platforms />
        <Faq />
      </main>
      <div className="relative z-1">
        <SiteFooter />
      </div>
    </>
  );
}
