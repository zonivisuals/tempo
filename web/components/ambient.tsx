/**
 * Ambient depth layers for the light canvas: a slow warm radial, a cool
 * neutral radial, a faded dot grid, and warm grain. Fixed and non-interactive
 * so it never affects layout or pointer events.
 */
export function AmbientLayers() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <div className="absolute inset-0 bg-[radial-gradient(48rem_32rem_at_78%_-6%,rgba(235,80,23,0.05),transparent_65%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(40rem_28rem_at_8%_12%,rgba(26,26,26,0.035),transparent_60%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(#D8D7D2_1px,transparent_1px)] [background-size:26px_26px] opacity-40 [mask-image:radial-gradient(60rem_50rem_at_50%_0%,black,transparent_75%)]" />
      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  );
}
