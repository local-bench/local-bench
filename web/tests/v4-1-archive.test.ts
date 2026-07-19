import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ARCHIVE_SHA256 = {
  "index-v4.1.json": "a880d031d4539b031f2bc5d51907b21bec896eac7c4cc7eca6ca5173113637cf",
  "agentic-v4.1.json": "3ed53d3433a1079696599263f65bff9b61d5318ecc7a1ce914e75f8fc23ce96f",
} as const;

describe("index-v4.1 archive preservation gate", () => {
  for (const [filename, expectedSha256] of Object.entries(ARCHIVE_SHA256)) {
    it(`preserves the byte-identical ${filename} snapshot`, async () => {
      const payload = await readFile(
        path.join(process.cwd(), "public", "data", "archive", filename),
      );

      expect(createHash("sha256").update(payload).digest("hex")).toBe(
        expectedSha256,
      );
    });
  }
});
