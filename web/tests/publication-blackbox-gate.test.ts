import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

const SUFFIX = "abcdef0123456789abcdef0123456789";
const communityDir = join(process.cwd(), "public", "data", "community");
const groupDir = join(communityDir, "groups");

afterAll(() => rmSync(communityDir, { force: true, recursive: true }));

describe("B2a production black-box release gate", () => {
  it("builds, serves, and renders two artifact-distinct variants on one isolated community page", async () => {
    mkdirSync(groupDir, { recursive: true });
    writeFileSync(join(communityDir, "index.json"), JSON.stringify({
      groups: [{ community_model_group_id: `community-group:${SUFFIX}`, group_path: `community/groups/${SUFFIX}.json`, n_variants: 2 }],
      schema_version: "localbench.community_publication.v1",
    }));
    writeFileSync(join(groupDir, `${SUFFIX}.json`), JSON.stringify({
      community_model_group_id: `community-group:${SUFFIX}`,
      identity_label: "community-declared, identity-unverified",
      ranked: false,
      schema_version: "localbench.community_publication.v1",
      variants: [variant("variant-one", "a"), variant("variant-two", "b")],
    }));
    const nextBin = join(process.cwd(), "node_modules", "next", "dist", "bin", "next");
    execFileSync(process.execPath, [nextBin, "build"], { cwd: process.cwd(), env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "pipe", timeout: 90_000 });
    const port = 31_000 + Math.floor(Math.random() * 1_000);
    const server = spawn(process.execPath, [join(process.cwd(), "tests", "fixtures", "static-server.mjs"), join(process.cwd(), "out"), String(port)], {
      cwd: process.cwd(), env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "pipe",
    });
    try {
      const html = await poll(`http://127.0.0.1:${port}/community/model/${SUFFIX}`);
      expect(html).toContain("community-declared, identity-unverified");
      expect(html).toContain("variant-one");
      expect(html).toContain("variant-two");
      expect((html.match(/<article/g) ?? [])).toHaveLength(2);
      expect(html).toContain("unranked");
    } finally {
      server.kill();
    }
  }, 120_000);
});

function variant(submission_id: string, hex: string) {
  return {
    artifact_sha256: hex.repeat(64), display_name: submission_id, projection_object_sha256: (hex === "a" ? "c" : "d").repeat(64),
    ranked: false, scores: { partial_composite: 0.5 }, submission_id,
  };
}

async function poll(url: string): Promise<string> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.text();
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw lastError;
}
