/**
 * Page copy. Every string on the landing page lives here so positioning
 * changes (e.g. which editor ships first) are a single-file edit.
 */

export const site = {
  name: "Tempo",
  domain: "tempo.editor",
  year: 2026,
  tagline: "Find any shot in your footage by describing it.",
} as const;

export const nav = {
  links: [
    { label: "Problem", href: "#problem" },
    { label: "How it works", href: "#how-it-works" },
    { label: "Demo", href: "#demo" },
    { label: "FAQ", href: "#faq" },
  ],
  cta: { label: "Join the waitlist", href: "#waitlist" },
} as const;

export const hero = {
  eyebrow: "For After Effects editors",
  title: "Search your footage the way you remember it.",
  description:
    "Tempo indexes every shot in your project — visuals, speech, faces — and finds the one you're thinking of. Type it, click it, you're on the frame.",
  form: {
    placeholder: "you@studio.com",
    cta: "Join the waitlist",
    note: "Early access opening in waves. No spam, one email when your invite is ready.",
  },
  demoLink: { label: "Watch the demo", href: "#demo" },
} as const;

export const audience = {
  title: "Built for the people who live in the timeline",
  roles: [
    "Freelance editors",
    "Motion designers",
    "Post-production studios",
    "Social & brand teams",
    "Documentary editors",
  ],
} as const;

export const problem = {
  eyebrow: "The daily tax",
  title: "Footage doesn't remember itself.",
  description:
    "Every editor knows the shot is in there somewhere. Finding it is the part that eats the day.",
  cards: [
    {
      title: "Filename roulette",
      body: "B-roll_final_v3_FINAL.mov tells you nothing. Neither does IMG_8842.",
    },
    {
      title: "Bin scrubbing",
      body: "Hover-previewing a hundred clips to recover the six seconds you remember.",
    },
    {
      title: "Hand-made labels",
      body: "Renaming, subclipping, tagging by hand — project after project — to keep footage findable later.",
    },
    {
      title: "The memory tax",
      body: "Client asks for the sunset take. You know it exists. Locating it costs the afternoon.",
    },
  ],
} as const;

export const howItWorks = {
  eyebrow: "How it works",
  title: "Three steps, once per project.",
  steps: [
    {
      number: "01",
      title: "Point it at your project",
      body: "Tempo scans the clips already in your composition or project. No renaming, no reorganizing, no extra copies to babysit.",
    },
    {
      number: "02",
      title: "Describe what you need",
      body: "“Drone shot over the city at night.” “Woman laughing, slow motion.” Plain words, not filenames or timecodes.",
    },
    {
      number: "03",
      title: "Jump to the shot",
      body: "Click a result and you land on the exact frame, marker placed. Scrub from there — the shot is already in your timeline.",
    },
  ],
} as const;

export const comparison = {
  eyebrow: "The difference",
  title: "Same footage. Two very different afternoons.",
  manual: {
    label: "Without Tempo",
    steps: [
      "Scrub the bin, clip by clip",
      "Preview 40 clips to find six seconds",
      "Rename what you need so you don't lose it again",
      "Ask a colleague if they've seen the file",
    ],
    elapsedLabel: "Elapsed",
    elapsedValue: "1h 47m",
  },
  tempo: {
    label: "With Tempo",
    elapsedLabel: "Elapsed",
    elapsedValue: "9 sec",
  },
} as const;

export const advantages = {
  eyebrow: "Why it feels different",
  title: "Speed you can feel on a deadline.",
  items: [
    {
      title: "Answers in seconds",
      body: "A query returns the exact shot and its timecode while a bin preview is still loading.",
      tag: "Speed",
      tone: "orange" as const,
    },
    {
      title: "Every project stays searchable",
      body: "Indexes persist between sessions, so last month's footage is as findable as the one you opened this morning.",
      tag: "Productivity",
      tone: "blue" as const,
    },
    {
      title: "Beyond filenames",
      body: "Searches visual content, spoken words, and faces at once — not just names you typed yourself.",
      tag: "Depth",
      tone: "green" as const,
    },
    {
      title: "Your footage stays yours",
      body: "Indexing runs against your own storage and workspace. Nothing lands on a shared server.",
      tag: "Privacy",
      tone: "yellow" as const,
    },
  ],
} as const;

export const platforms = {
  eyebrow: "Platforms",
  title: "After Effects first. The rest of your suite next.",
  live: {
    name: "After Effects",
    status: "Available at launch",
    detail: "Native panel for the current release on macOS and Windows.",
  },
  roadmap: [
    {
      name: "Premiere Pro",
      detail: "Same search, applied to sequences.",
    },
    {
      name: "DaVinci Resolve",
      detail: "Cut page included.",
    },
  ],
  waitlistNote: "Waitlist members get the next platform first.",
} as const;

export const faq = {
  eyebrow: "FAQ",
  title: "Straight answers.",
  items: [
    {
      q: "Which versions of After Effects are supported?",
      a: "Tempo ships as a native panel for the current After Effects release, on macOS and Windows.",
    },
    {
      q: "What does Tempo actually index?",
      a: "The visual content of every shot, spoken audio through on-device transcription, and detected faces. Search runs across all three at once.",
    },
    {
      q: "Does it need my footage online or processed in advance?",
      a: "No. Tempo works from the footage already in your project. The first scan happens once, then results are instant.",
    },
    {
      q: "How long does indexing take?",
      a: "A few minutes per hour of footage on a typical machine, running in the background while you keep working.",
    },
    {
      q: "Will it work with Premiere Pro or DaVinci Resolve?",
      a: "Both are on the roadmap, and the waitlist hears the moment either is ready.",
    },
    {
      q: "How much will it cost?",
      a: "Pricing lands before launch. Waitlist members hear first, with the best early terms.",
    },
  ],
} as const;

export const finalCta = {
  title: "Stop scrubbing. Start describing.",
  description:
    "Join the waitlist for early access to Tempo for After Effects — and first dibs when Premiere Pro and DaVinci Resolve arrive.",
} as const;

export const footer = {
  note: "Built for editors.",
  links: [
    { label: "Join the waitlist", href: "#waitlist" },
    { label: "Demo", href: "#demo" },
    { label: "FAQ", href: "#faq" },
  ],
} as const;
