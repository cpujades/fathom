import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import "./globals.css";

export const metadata: Metadata = {
  title: "Talven | Private Podcast Briefings",
  description: "Turn long podcast episodes into clear, timestamped briefings built for private advantage.",
  openGraph: {
    title: "Talven | Private Podcast Briefings",
    description: "Paste a YouTube podcast URL and get a concise, timestamped briefing.",
    type: "website"
  },
  twitter: {
    card: "summary_large_image",
    title: "Talven | Private Podcast Briefings",
    description: "Convert long podcast episodes into fast, readable briefings with source moments attached."
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`} data-scroll-behavior="smooth">
      <body className={GeistSans.className}>{children}</body>
    </html>
  );
}
