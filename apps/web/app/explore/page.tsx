import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@fathom/api-client";

import { PublicHeader } from "../components/PublicHeader";
import { formatExploreTopic } from "../lib/format";
import { ExploreGrid } from "./ExploreGrid";
import styles from "./explore.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Explore source-linked briefings | Talven",
  description: "Read a small collection of source-linked briefings selected by Talven.",
  alternates: { canonical: "/explore" },
  robots: { index: false, follow: false }
};

type ExplorePageProps = {
  searchParams: Promise<{ topic?: string | string[] }>;
};

export default async function ExplorePage({ searchParams }: ExplorePageProps) {
  const params = await searchParams;
  const topicValue = Array.isArray(params.topic) ? params.topic[0] : params.topic;
  const topic = topicValue?.trim() || undefined;
  const api = createApiClient();
  const { data, error } = await api.GET("/explore", {
    params: { query: { limit: 48, offset: 0, topic: topic ?? null } },
    cache: "no-store"
  });
  if (error || !data) throw new Error("Unable to load Explore.");
  const selectedTopic = data.topic;

  return (
    <div className={styles.page}>
      <PublicHeader />
      <main id="main-content" className={styles.main}>
        <header className={styles.hero}>
          <p>Curated by Talven</p>
          <h1>Explore ideas worth keeping.</h1>
          <div className={styles.heroBottom}>
            <span>Read freely. Save useful briefings to your private library without using video time.</span>
            {selectedTopic ? <Link href="/explore">Clear topic: {formatExploreTopic(selectedTopic)}</Link> : null}
          </div>
        </header>

        <nav className={styles.topicFilters} aria-label="Explore topics">
          <Link href="/explore" aria-current={selectedTopic ? undefined : "page"}>All</Link>
          {data.available_topics.map((value) => (
            <Link
              href={`/explore?topic=${encodeURIComponent(value)}`}
              aria-current={selectedTopic === value ? "page" : undefined}
              key={value}
            >
              {formatExploreTopic(value)}
            </Link>
          ))}
        </nav>

        {data.items.length ? (
          <ExploreGrid items={data.items} />
        ) : (
          <section className={styles.emptyState}>
            <h2>
              {selectedTopic
                ? `No ${formatExploreTopic(selectedTopic)} briefings yet`
                : "The first collection is being prepared"}
            </h2>
            <p>Talven will keep this catalogue small and useful.</p>
            {selectedTopic ? <Link href="/explore">View all topics</Link> : <Link href="/signup">Create new briefing</Link>}
          </section>
        )}
      </main>
    </div>
  );
}
