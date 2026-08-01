import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://talven.ai"),
  title: "Talven | Private YouTube Briefings",
  description: "Turn long-form YouTube videos into clear, evidence-linked briefings you can reuse.",
  applicationName: "Talven",
  alternates: {
    canonical: "/"
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    shortcut: "/favicon.svg"
  },
  openGraph: {
    title: "Talven | Private YouTube Briefings",
    description: "Paste a public YouTube URL and get a concise, timestamped briefing.",
    url: "/",
    siteName: "Talven",
    type: "website",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Talven private YouTube briefings"
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: "Talven | Private YouTube Briefings",
    description: "Convert long-form YouTube videos into fast, readable briefings with source moments attached.",
    images: ["/opengraph-image"]
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`} data-scroll-behavior="smooth">
      <body className={GeistSans.className}>
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
