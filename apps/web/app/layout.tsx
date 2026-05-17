import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://talven.ai"),
  title: "Talven | Private Podcast Briefings",
  description: "Turn long podcast episodes into clear, timestamped briefings built for private advantage.",
  applicationName: "Talven",
  alternates: {
    canonical: "/"
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    shortcut: "/favicon.svg"
  },
  openGraph: {
    title: "Talven | Private Podcast Briefings",
    description: "Paste a YouTube podcast URL and get a concise, timestamped briefing.",
    url: "/",
    siteName: "Talven",
    type: "website",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "Talven private podcast briefings"
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: "Talven | Private Podcast Briefings",
    description: "Convert long podcast episodes into fast, readable briefings with source moments attached.",
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
