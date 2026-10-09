import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";

export const alt = "Tempo — search your footage the way you remember it";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

async function loadSerifFont() {
  try {
    const buffer = await readFile(
      join(process.cwd(), "app", "fonts", "InstrumentSerif.ttf"),
    );
    return buffer;
  } catch {
    return null;
  }
}

export default async function OpengraphImage() {
  const fontData = await loadSerifFont();

  const fonts = fontData
    ? [{ name: "Instrument Serif", data: fontData, style: "normal" as const }]
    : [];

  const serif = fonts.length ? '"Instrument Serif", serif' : "serif";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          backgroundColor: "#F7F6F3",
          padding: "72px",
          fontFamily: serif,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              backgroundColor: "#232323",
              color: "#FFFFFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 26,
              fontWeight: 600,
            }}
          >
            T
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 26,
              letterSpacing: 8,
              color: "#1A1A1A",
              fontWeight: 600,
              fontFamily: "sans-serif",
            }}
          >
            <span style={{ color: "#EB5017" }}>T</span>EMPO
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              fontSize: 74,
              lineHeight: 1.05,
              letterSpacing: -2,
              color: "#1A1A1A",
              fontFamily: serif,
              maxWidth: 920,
            }}
          >
            Search your footage the way you remember it.
          </div>
          <div
            style={{
              fontSize: 26,
              color: "#787774",
              maxWidth: 780,
              fontFamily: "sans-serif",
            }}
          >
            Semantic search for video editors. Describe a shot, jump to the frame.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 999,
              backgroundColor: "#EB5017",
            }}
          />
          <div
            style={{
              fontSize: 20,
              color: "#787774",
              letterSpacing: 4,
              fontFamily: "sans-serif",
            }}
          >
            TEMPO.EDITOR
          </div>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}

