import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_SUITE_MANIFEST_SHA256,
  DEFAULT_SUITE_RELEASE_ID,
} from "../functions/_lib/submission-contracts";
import { PUBLIC_SUITES } from "../functions/_lib/suite-catalog";
import { SUITE_MANIFEST_SHA, SUITE_RELEASE_ID } from "./submission-test-support";
import { FIVE_AXIS_SUITE_MANIFEST_SHA, FIVE_AXIS_SUITE_RELEASE_ID } from "./submission-contract-v2-support";

// Regression guard for the 2026-07-06 manifest-sha desync. The per-release suite_manifest_sha256
// is duplicated across the CLI (release-pairs.expected.json, foundation._SITE_RELEASED_SUITES) and
// the web (suite-catalog, submission-contracts default, two test-support constants). A scorer-
// identity bump updated only the CLI fixture, leaving five web/CLI sites stale — which would have
// made the server reject every v2 bundle. release-pairs.expected.json is the single source of
// truth (itself parity-checked against the live CLI computation in
// test_cli_release_pairs_match_shared_fixture). Every web-side copy must match it.
const fixture = JSON.parse(
  readFileSync(new URL("../../suite/release-pairs.expected.json", import.meta.url), "utf-8"),
) as { readonly pairs: readonly { readonly id: string; readonly suite_manifest_sha256: string }[] };

const shaByRelease = new Map(fixture.pairs.map((pair) => [pair.id, pair.suite_manifest_sha256]));

// core-text-v1 is an early diagnostic suite that predates the release-pair naming and has no
// published release manifest, so it is intentionally absent from the source of truth. Any OTHER
// catalog suite missing from the fixture is a real gap and must fail.
const CATALOG_SUITES_WITHOUT_RELEASE_PAIR = new Set(["core-text-v1"]);

describe("suite manifest sha parity across all web references", () => {
  it("server catalog (PUBLIC_SUITES) matches the release-pairs source of truth", () => {
    for (const suite of PUBLIC_SUITES) {
      const expected = shaByRelease.get(suite.id);
      if (expected === undefined) {
        expect(
          CATALOG_SUITES_WITHOUT_RELEASE_PAIR.has(suite.id),
          `${suite.id} is a catalog suite with no release-pairs entry (add it to the fixture, or to the known-absent allowlist)`,
        ).toBe(true);
        continue;
      }
      expect(suite.suiteManifestSha256, `catalog sha for ${suite.id}`).toBe(expected);
    }
  });

  it("submission-contracts default matches its declared release", () => {
    expect(DEFAULT_SUITE_MANIFEST_SHA256).toBe(shaByRelease.get(DEFAULT_SUITE_RELEASE_ID));
  });

  it("test-support fixture constants match their declared releases", () => {
    expect(SUITE_MANIFEST_SHA).toBe(shaByRelease.get(SUITE_RELEASE_ID));
    expect(FIVE_AXIS_SUITE_MANIFEST_SHA).toBe(shaByRelease.get(FIVE_AXIS_SUITE_RELEASE_ID));
  });
});
