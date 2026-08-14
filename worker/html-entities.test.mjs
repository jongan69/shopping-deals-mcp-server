import { expect, test } from "bun:test";

import { decodeHtml } from "./html-entities.ts";

test("decodes supported HTML entities exactly once", () => {
  expect(decodeHtml("&amp;lt;deal&amp;gt; &quot;x&quot; &#39;y&#39;"))
    .toBe("&lt;deal&gt; \"x\" 'y'");
});
