import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import "./globals.css";

export const metadata: Metadata = {
  title: "Fathom | YouTube Podcast Summaries",
  description: "Turn YouTube podcast episodes into concise, timestamped summaries in minutes.",
  openGraph: {
    title: "Fathom | YouTube Podcast Summaries",
    description: "Paste a YouTube podcast URL and get a concise, timestamped summary.",
    type: "website"
  },
  twitter: {
    card: "summary_large_image",
    title: "Fathom | YouTube Podcast Summaries",
    description: "Summarize long YouTube podcast episodes into fast, readable briefs."
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className={GeistSans.className}>{children}</body>
    </html>
  );
}
