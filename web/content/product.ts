/**
 * Product capture model. Every state here is a success state — the landing
 * page deliberately shows Tempo working, never loading, empty, or failing.
 */

export type ShotTile = {
  id: string;
  src: string;
  caption: string;
  duration: string;
};

export type QueryScenario = {
  id: string;
  query: string;
  tiles: ShotTile[];
};

export const searchPlaceholder = "Search for anything";

export const scenarios: QueryScenario[] = [
  {
    id: "skyline",
    query: "drone shot over city skyline at sunset",
    tiles: [
      { id: "s1", src: "/frames/skyline-a.jpg", caption: "golden hour aerial over downtown", duration: "4s" },
      { id: "s2", src: "/frames/skyline-b.jpg", caption: "slow descent toward rooftop level", duration: "6s" },
      { id: "s3", src: "/frames/skyline-c.jpg", caption: "hazy sun between two towers", duration: "3s" },
      { id: "s4", src: "/frames/skyline-d.jpg", caption: "river bend, warm sidelight", duration: "5s" },
      { id: "s5", src: "/frames/skyline-e.jpg", caption: "night skyline from the bridge", duration: "7s" },
      { id: "s6", src: "/frames/skyline-f.jpg", caption: "aerial follow along the highway", duration: "9s" },
    ],
  },
  {
    id: "ocean",
    query: "waves crashing on dark rocks at dawn",
    tiles: [
      { id: "o1", src: "/frames/ocean-a.jpg", caption: "first light on the water", duration: "4s" },
      { id: "o2", src: "/frames/ocean-b.jpg", caption: "wave hitting volcanic rock", duration: "5s" },
      { id: "o3", src: "/frames/ocean-c.jpg", caption: "long exposure of the shore", duration: "3s" },
      { id: "o4", src: "/frames/ocean-d.jpg", caption: "long exposure of the shore", duration: "8s" },
      { id: "o5", src: "/frames/ocean-e.jpg", caption: "sea birds over the surf", duration: "6s" },
      { id: "o6", src: "/frames/ocean-f.jpg", caption: "mist lifting off the coast", duration: "7s" },
    ],
  },
];

/** The reel steps, all success states, used by hero and demo section. */
export const reelSteps = [
  { id: "typing", label: "Query in plain words" },
  { id: "results", label: "Matching shots" },
  { id: "marker", label: "Jump to the frame" },
] as const;

export const markerTimecode = "00:01:12:04";

export const projectName = "Nike_Spot_Q4.aep";
