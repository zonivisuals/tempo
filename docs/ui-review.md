# UI review gate (AGENTS.md §6, F6-minimal)

Before release, screenshot the panel docked next to a native AE panel
(Project or Timeline) at 100% scaling and walk this list. Any reviewer can
flag and reject an element reading as "AI-generated slop".

## Must hold

- [ ] Flat surfaces, 1px borders, corner radius ≤ 2px everywhere.
- [ ] 12px base / 11px metadata, system font stack, 4px spacing rhythm.
- [ ] Monochrome + at most one accent, used only for selection/active.
- [ ] Progress = thin flat bars; loading = opacity-pulsing skeletons only.
- [ ] Indexing section: one always-visible summary line ("Indexing ·
      interview.mp4 · Speech 212/481 s", or "3 footage · 3 ready") and a
      16px monochrome eye toggle (accent only while the detail is shown).
      Detail opens when a job starts, hides when jobs finish or a search runs,
      and stays open when a job failed.
- [ ] Short factual labels ("Indexing · OCR 37/157"); result cards show
      thumbnail, file name, timecode range + duration, transcript/caption
      and one Insert action — no score bars, no percentages.
- [ ] Errors are compact inline rows with the service error code — no modals,
      no toasts, no spinners where skeletons belong.
- [ ] Offline service renders a usable degraded state (search disabled
      honestly, sync reports `SERVICE_OFFLINE`), never a blank panel.

## Instant reject

Gradients, glows, glassmorphism, decorative shadows, big-radius cards,
pills, purple/blue AI palettes, emoji UI, "Ask anything…"/"Powered by"
copy, exclamation marks, animated backgrounds.
