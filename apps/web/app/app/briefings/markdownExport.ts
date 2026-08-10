type ClipboardWriter = {
  writeText(text: string): Promise<void>;
};

export function buildMarkdownExport(markdown: string): string {
  if (!markdown.trim()) {
    return "";
  }

  return markdown.endsWith("\n") ? markdown : `${markdown}\n`;
}

export async function copyMarkdownToClipboard(
  markdown: string,
  clipboard: ClipboardWriter | null | undefined
): Promise<void> {
  const exportContent = buildMarkdownExport(markdown);

  if (!exportContent) {
    throw new Error("Briefing Markdown is unavailable.");
  }
  if (!clipboard) {
    throw new Error("Clipboard access is unavailable.");
  }

  await clipboard.writeText(exportContent);
}
