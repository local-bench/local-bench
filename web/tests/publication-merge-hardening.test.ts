import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { describe, it } from "vitest";

const cases = [
  ["rejects a parent-directory community group id", "invalid_group_parent"],
  ["rejects a non-hex community group id", "invalid_group_nonhex"],
  ["rejects malformed projection and artifact digests", "bad_digest"],
  ["removes a stale group after suppression", "stale_group"],
  ["left-joins lineage without emitting unmatched overlay entries", "overlay_left_join"],
  ["records the lineage overlay bytes digest", "overlay_digest"],
  ["rejects invalid and unknown score fields", "score_shape"],
  ["leaves the prior community tree intact when staged validation fails", "atomic_validation"],
] as const;

describe("publication merge hardening", () => {
  it.each(cases)("%s", (_name, caseName) => {
    execFileSync(
      process.env["LOCALBENCH_PYTHON"] ?? "python",
      [join(process.cwd(), "tests", "fixtures", "publication_merge_case.py"), caseName],
      { cwd: process.cwd(), stdio: "pipe", timeout: 30_000 },
    );
  });
});
