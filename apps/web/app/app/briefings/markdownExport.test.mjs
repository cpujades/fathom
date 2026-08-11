import assert from "node:assert/strict";
import test from "node:test";

import { buildMarkdownExport, copyMarkdownToClipboard } from "./markdownExport.ts";

test("Markdown exports preserve content and end with one existing or added newline", () => {
  assert.equal(buildMarkdownExport("# Briefing"), "# Briefing\n");
  assert.equal(buildMarkdownExport("# Briefing\n"), "# Briefing\n");
  assert.equal(buildMarkdownExport("# Briefing\n\n"), "# Briefing\n\n");
  assert.equal(buildMarkdownExport("  \n"), "");
});

test("Copy Markdown writes the exact downloadable export once", async () => {
  const writes = [];
  const clipboard = {
    async writeText(value) {
      writes.push(value);
    }
  };

  await copyMarkdownToClipboard("# Briefing\n\n[Moment](https://youtu.be/example?t=42)", clipboard);

  assert.deepEqual(writes, ["# Briefing\n\n[Moment](https://youtu.be/example?t=42)\n"]);
});

test("Copy Markdown rejects unavailable content without touching the clipboard", async () => {
  let writeCount = 0;
  const clipboard = {
    async writeText() {
      writeCount += 1;
    }
  };

  await assert.rejects(() => copyMarkdownToClipboard("", clipboard), /unavailable/i);
  assert.equal(writeCount, 0);
});

test("Copy Markdown reports unavailable or rejected clipboard access", async () => {
  await assert.rejects(() => copyMarkdownToClipboard("# Briefing", undefined), /clipboard access/i);
  await assert.rejects(
    () => copyMarkdownToClipboard("# Briefing", { writeText: async () => Promise.reject(new Error("Denied")) }),
    /Denied/
  );
});
