export type TakeawayItem = {
  title: string;
  bodyMarkdown: string;
};

const cleanTakeawayTitle = (value: string): string => {
  return value
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
};

export const parseTakeawayItems = (markdown: string): TakeawayItem[] => {
  const items: TakeawayItem[] = [];
  const itemPattern = /^\s*(?:[-*+]\s*)?\*\*(.+?)(?::\*\*|\*\*\s*:?)\s*(.+)$/;

  for (const line of markdown.split("\n")) {
    const match = itemPattern.exec(line);
    if (!match) {
      continue;
    }
    const title = cleanTakeawayTitle(match[1]);
    const bodyMarkdown = match[2].trim();

    if (title && bodyMarkdown) {
      items.push({ title, bodyMarkdown });
    }
  }

  return items;
};
