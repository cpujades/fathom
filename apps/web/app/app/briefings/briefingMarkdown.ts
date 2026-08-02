export type ParsedBriefingSection = {
  id: string;
  level: number;
  title: string;
  content: string;
};

export type ParsedBriefing = {
  title: string;
  summary: string;
  takeaways: string;
  articleSections: ParsedBriefingSection[];
  references: ParsedBriefingSection | null;
};

export type BriefingSectionKind = "deepRead" | "standard";

export function removeGenericBriefingHeading(markdown: string): string {
  return markdown.replace(/^#\s+(briefing|podcast briefing|summary)\s*\n+/i, "");
}

export function parseBriefingMarkdown(markdown: string, fallbackTitle?: string | null): ParsedBriefing {
  const cleanedMarkdown = normalizeBriefingMarkdown(markdown).trim();
  const sections = splitMarkdownSections(cleanedMarkdown);
  const titleSection = sections.find((section) => section.level === 1 && !isGenericTitle(section.title));
  const title = titleSection?.title || fallbackTitle || "Untitled briefing";
  const summarySection = sections.find((section) => isSummaryHeading(section.title));
  const takeawaysSection = sections.find((section) => isTakeawaysHeading(section.title));
  const referencesSection = sections.find((section) => isReferencesHeading(section.title)) ?? null;
  const bodySections = sections.filter(
    (section) =>
      section !== titleSection &&
      section !== summarySection &&
      section !== takeawaysSection &&
      section !== referencesSection &&
      section.content.trim()
  );
  const hasRecognizedStructure = Boolean(
    titleSection || summarySection || takeawaysSection || referencesSection || bodySections.length
  );

  const articleSections = bodySections.length
    ? bodySections.map((section) => ({ ...section, title: humanizeSectionTitle(section.title) }))
    : cleanedMarkdown && !hasRecognizedStructure
      ? [{ id: "briefing-notes", level: 2, title: "Briefing notes", content: cleanedMarkdown }]
      : [];

  return {
    title,
    summary: summarySection?.content.trim() ?? "",
    takeaways: takeawaysSection?.content.trim() ?? "",
    articleSections,
    references: referencesSection
      ? { ...referencesSection, title: humanizeSectionTitle(referencesSection.title) }
      : null
  };
}

export function getSectionKind(title: string): BriefingSectionKind {
  return /detailed|briefing|summary/i.test(title) ? "deepRead" : "standard";
}

export function getSectionDisplayTitle(title: string, kind: BriefingSectionKind): string {
  return kind === "deepRead" && /detailed/i.test(title) ? "Deeper read" : title;
}

export function getMobileSectionLabel(label: string): string {
  if (/references?|sources?/i.test(label)) {
    return "Sources";
  }
  if (/detailed|deeper/i.test(label)) {
    return "Details";
  }
  return label.length > 14 ? "Section" : label;
}

export function emphasizeFirstSentence(markdown: string): string {
  const trimmed = markdown.trim();
  if (!trimmed || trimmed.startsWith("**") || trimmed.startsWith("#") || trimmed.includes("\n- ")) {
    return markdown;
  }

  const sentenceMatch = /^(.+?[.!?])(\s+.+)$/s.exec(trimmed);
  return sentenceMatch ? `**${sentenceMatch[1]}**${sentenceMatch[2]}` : markdown;
}

function splitMarkdownSections(markdown: string): ParsedBriefingSection[] {
  if (!markdown.trim()) {
    return [];
  }

  const lines = markdown.split(/\r?\n/);
  const sections: Array<ParsedBriefingSection & { contentLines: string[] }> = [];
  let current: (ParsedBriefingSection & { contentLines: string[] }) | null = null;
  const prefaceLines: string[] = [];

  for (const line of lines) {
    const headingMatch = /^(#{1,2})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!headingMatch) {
      (current ? current.contentLines : prefaceLines).push(line);
      continue;
    }

    if (current) {
      current.content = current.contentLines.join("\n").trim();
      sections.push(current);
    }

    const title = cleanInlineMarkdown(headingMatch[2]);
    current = {
      id: getSectionId(title, sections.length),
      level: headingMatch[1].length,
      title,
      content: "",
      contentLines: []
    };
  }

  if (current) {
    current.content = current.contentLines.join("\n").trim();
    sections.push(current);
  }

  const preface = prefaceLines.join("\n").trim();
  if (preface) {
    sections.unshift({
      id: "briefing-overview",
      level: 2,
      title: "Overview",
      content: preface,
      contentLines: []
    });
  }

  return sections.map(({ contentLines: _contentLines, ...section }) => section);
}

function normalizeBriefingMarkdown(markdown: string): string {
  const withoutDecorations = markdown
    .replace(/^(\s*[-*+]\s*)(?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*/gmu, "$1")
    .replace(/^((?:[\u2705\u26a0\ufe0f]|\u{1f4a1})\s*)+/gmu, "");
  return normalizeLooseSectionHeadings(withoutDecorations);
}

function normalizeLooseSectionHeadings(markdown: string): string {
  const lines = markdown.split(/\r?\n/);
  const normalizedLines: string[] = [];
  let sawHeading = false;
  let sawKnownSection = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = cleanInlineMarkdown(line);

    if (/^#{1,6}\s+/.test(line.trim())) {
      sawHeading = true;
      normalizedLines.push(line);
      continue;
    }

    const knownSectionTitle = getKnownBriefingSectionTitle(trimmed);
    if (knownSectionTitle) {
      sawHeading = true;
      sawKnownSection = true;
      normalizedLines.push(`## ${knownSectionTitle}`);
      continue;
    }

    const isFirstMeaningfulLine = !sawHeading && trimmed && !line.trim().startsWith("-") && !line.trim().startsWith("*");
    const nextKnownSection = getKnownBriefingSectionTitle(getNextMeaningfulLine(lines, index));
    if (isFirstMeaningfulLine && nextKnownSection) {
      sawHeading = true;
      normalizedLines.push(`# ${trimmed}`);
      continue;
    }

    normalizedLines.push(line);
  }

  return sawKnownSection ? normalizedLines.join("\n") : markdown;
}

function getNextMeaningfulLine(lines: string[], currentIndex: number): string {
  for (let index = currentIndex + 1; index < lines.length; index += 1) {
    const nextLine = cleanInlineMarkdown(lines[index]);
    if (nextLine) {
      return nextLine;
    }
  }
  return "";
}

function getKnownBriefingSectionTitle(value: string): string | null {
  const normalized = value.replace(/:$/, "").toLowerCase();
  if (/^brief in (?:30|thirty) seconds$/.test(normalized) || normalized === "brief") return "Brief in 30 seconds";
  if (/^key takeaways?$/.test(normalized) || normalized === "what matters") return "Key Takeaways";
  if (/^(?:detailed|deep|full) briefing$/.test(normalized) || normalized === "deeper read") return "Detailed Briefing";
  if (/^highlights?(?: & | and )quotes?$/.test(normalized)) return "Highlights & Quotes";
  if (/^action items?$/.test(normalized)) return "Action Items";
  if (/^next steps?$/.test(normalized)) return "Next Steps";
  if (/^open questions?$/.test(normalized)) return "Open Questions";
  if (/^(?:references|sources)$/.test(normalized)) return "References";
  return null;
}

function cleanInlineMarkdown(value: string): string {
  return value.replace(/[*_`~]/g, "").replace(/\s+/g, " ").trim();
}

function humanizeSectionTitle(value: string): string {
  return /^tl;?dr$/i.test(value.trim()) ? "Summary" : value;
}

function getSectionId(title: string, index: number): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 48);
  return `briefing-${slug || "section"}-${index}`;
}

function isGenericTitle(title: string): boolean {
  return /^(briefing|podcast briefing|summary)$/i.test(title.trim());
}

function isSummaryHeading(title: string): boolean {
  const normalized = title.toLowerCase().replace(/[^\w]+/g, "");
  return normalized === "tldr" || normalized === "summary" || normalized === "briefin30seconds";
}

function isTakeawaysHeading(title: string): boolean {
  return /takeaways?/i.test(title);
}

function isReferencesHeading(title: string): boolean {
  return /references?|sources?/i.test(title);
}
