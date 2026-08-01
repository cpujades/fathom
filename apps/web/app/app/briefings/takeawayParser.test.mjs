import assert from "node:assert/strict";
import test from "node:test";

import { parseTakeawayItems } from "./takeawayParser.ts";

test("takeaway parsing preserves source-linked timestamp Markdown", () => {
  const items = parseTakeawayItems(`- **Verify the central claim:** Compare the original explanation [12:34–13:08](https://www.youtube.com/watch?v=video123&t=754s)
- **Keep the caveat:** The speaker limits the conclusion [21:04–21:22](https://www.youtube.com/watch?v=video123&t=1264s)`);

  assert.deepEqual(items, [
    {
      title: "Verify the central claim",
      bodyMarkdown:
        "Compare the original explanation [12:34–13:08](https://www.youtube.com/watch?v=video123&t=754s)"
    },
    {
      title: "Keep the caveat",
      bodyMarkdown:
        "The speaker limits the conclusion [21:04–21:22](https://www.youtube.com/watch?v=video123&t=1264s)"
    }
  ]);
});

test("takeaway parsing leaves unsupported shapes to the safe full Markdown renderer", () => {
  assert.deepEqual(parseTakeawayItems("- A normal Markdown bullet"), []);
});
