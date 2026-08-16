import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { createApiClient, type PublicBriefingResponse } from "@fathom/api-client";

import { PublicationSaveAction } from "../../components/PublicationSaveAction";
import { PublicHeader } from "../../components/PublicHeader";
import { StreamingMarkdown } from "../../components/StreamingMarkdown";
import { formatExactDuration, formatExploreTopic } from "../../lib/format";
import styles from "./public-briefing.module.css";

export const dynamic = "force-dynamic";

type PublicBriefingPageProps = {
  params: Promise<{ publicSlug: string }>;
};

const loadPublicBriefing = cache(async (publicSlug: string): Promise<PublicBriefingResponse | null> => {
  const api = createApiClient();
  const { data, error, response } = await api.GET("/publications/{public_slug}", {
    params: { path: { public_slug: publicSlug } },
    cache: "no-store"
  });
  if (response.status === 404) return null;
  if (error || !data) throw new Error("Unable to load this public briefing.");
  return data;
});

export async function generateMetadata({ params }: PublicBriefingPageProps): Promise<Metadata> {
  const { publicSlug } = await params;
  const briefing = await loadPublicBriefing(publicSlug);
  if (!briefing) return { title: "Briefing unavailable | Talven", robots: { index: false, follow: false } };

  const description = briefing.author
    ? `A source-linked briefing of ${briefing.title} by ${briefing.author}.`
    : `A source-linked briefing of ${briefing.title}.`;
  return {
    title: `${briefing.title} | Talven`,
    description,
    alternates: { canonical: briefing.public_path },
    robots: { index: false, follow: false },
    openGraph: {
      title: briefing.title,
      description,
      type: "article",
      url: briefing.public_path,
      images: briefing.source_thumbnail_url ? [{ url: briefing.source_thumbnail_url }] : undefined
    },
    twitter: {
      card: briefing.source_thumbnail_url ? "summary_large_image" : "summary",
      title: briefing.title,
      description,
      images: briefing.source_thumbnail_url ? [briefing.source_thumbnail_url] : undefined
    }
  };
}

export default async function PublicBriefingPage({ params }: PublicBriefingPageProps) {
  const { publicSlug } = await params;
  const briefing = await loadPublicBriefing(publicSlug);
  if (!briefing) notFound();

  return (
    <div className={styles.page}>
      <PublicHeader />
      <main id="main-content" className={styles.main}>
        <header className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.eyebrowRow}>
              <span>
                {briefing.visibility === "listed" && briefing.topic
                  ? formatExploreTopic(briefing.topic)
                  : "Shared briefing"}
              </span>
              <span>Source-linked by Talven</span>
            </div>
            <h1>{briefing.title}</h1>
            <div className={styles.sourceMeta}>
              {briefing.author ? <span>By {briefing.author}</span> : null}
              {briefing.source_duration_seconds ? (
                <span>{formatExactDuration(briefing.source_duration_seconds)}</span>
              ) : null}
              <a href={briefing.source_url} target="_blank" rel="noreferrer">Open original source</a>
            </div>
            <p className={styles.heroText}>Read the useful ideas, then save the briefing to your private library.</p>
            <div className={styles.heroActions}>
              <PublicationSaveAction publicPath={briefing.public_path} publicSlug={briefing.public_slug} />
              <Link href="/app">Create new briefing</Link>
            </div>
          </div>
          {briefing.source_thumbnail_url ? (
            <div className={styles.thumbnailFrame}>
              <Image
                className={styles.thumbnail}
                src={briefing.source_thumbnail_url}
                alt=""
                fill
                priority
                sizes="(max-width: 760px) 92vw, 360px"
              />
            </div>
          ) : null}
        </header>

        <article className={styles.reader}>
          <StreamingMarkdown markdown={briefing.markdown} className={styles.markdown} />
        </article>

        <footer className={styles.footer}>
          <p>Briefed with Talven. Material claims link back to their source moments.</p>
          <Link href="/explore">Explore more briefings</Link>
        </footer>
      </main>
    </div>
  );
}
