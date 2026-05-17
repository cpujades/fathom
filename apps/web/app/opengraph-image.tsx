import { ImageResponse } from "next/og";

export const alt = "Talven private podcast briefings";
export const size = {
  width: 1200,
  height: 630
};
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          padding: 56,
          color: "#18211d",
          background:
            "radial-gradient(circle at 16% 18%, rgba(40, 92, 70, 0.22), transparent 32%), radial-gradient(circle at 84% 6%, rgba(142, 123, 73, 0.18), transparent 30%), linear-gradient(135deg, #faf7f0 0%, #f0eadf 55%, #dfe8dd 100%)"
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            border: "1px solid rgba(35, 55, 45, 0.16)",
            borderRadius: 42,
            padding: 46,
            background: "linear-gradient(180deg, rgba(249,246,239,0.88), rgba(230,237,228,0.68))",
            boxShadow: "0 32px 90px rgba(18, 28, 23, 0.16)"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "linear-gradient(145deg, #285c46, #17382b)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#e8dbbd",
                fontSize: 26,
                fontWeight: 800
              }}
            >
              T
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 18, color: "#667267", letterSpacing: 2.4, textTransform: "uppercase" }}>
                Private podcast briefings
              </span>
              <span style={{ fontSize: 34, fontWeight: 800 }}>Talven</span>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <h1
              style={{
                margin: 0,
                maxWidth: 760,
                fontSize: 82,
                lineHeight: 0.95,
                letterSpacing: -2.2,
                fontWeight: 800
              }}
            >
              Extract the signal. Keep the edge.
            </h1>
            <p style={{ margin: 0, maxWidth: 760, color: "#435247", fontSize: 30, lineHeight: 1.35 }}>
              Turn long podcast conversations into clear, source-linked briefings ready to read, verify, and reuse.
            </p>
          </div>

          <div style={{ display: "flex", gap: 14, color: "#17382b", fontSize: 24, fontWeight: 700 }}>
            <span>YouTube link in</span>
            <span>/</span>
            <span>Briefing out</span>
            <span>/</span>
            <span>Markdown + PDF ready</span>
          </div>
        </div>
      </div>
    ),
    size
  );
}
