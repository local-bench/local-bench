import { execFileSync, spawn } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "@playwright/test";
import { afterAll, describe, expect, it } from "vitest";
import { canonicalJson } from "../functions/_lib/submission-canonical";
import {
  handleActivatePublicationSnapshot,
  handleCreatePublicationSnapshot,
  handleExportPublicationSnapshot,
  handleServeActivePublicationSnapshot,
} from "../functions/_lib/publication-snapshot";
import { persistProjectionCreateOnly } from "../functions/_lib/publication-storage";
import { transitionAcceptedToTerminal } from "../functions/_lib/submission-store";
import { getCommunityGroup } from "../lib/data";
import { onRequestPost as applyDecision } from "../functions/api/admin/submissions/[submissionId]/decision";
import { onRequestPost as applyVerification } from "../functions/api/admin/submissions/[submissionId]/verification";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { communityTicketBody, signedResultBundle, testKeyPair } from "./submission-contract-v2-support";
import {
  ADMIN_SECRET, MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009,
  MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, TEST_COMMUNITY_GROUP_ID, createEnv, getRequest, jsonRequest, sha256Hex, statusUpdate,
  type IssuedEnvelope,
} from "./submission-test-support";

const SUFFIX = TEST_COMMUNITY_GROUP_ID.replace("community-group:", "");
const MIGRATIONS = [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013];
const communityDir = join(process.cwd(), "public", "data", "community");
const tempRoot = mkdtempSync(join(tmpdir(), "b2a-blackbox-"));

afterAll(() => {
  rmSync(communityDir, { force: true, recursive: true });
  rmSync(tempRoot, { force: true, recursive: true });
});

/**
 * This is the strongest in-repository A9 gate: real Worker handler entrypoints run on
 * Miniflare D1/R2 bindings, followed by the production exporter/merge and HTTP-served
 * static build. A clean-machine Wrangler/Cloudflare HTTP canary remains a manual release
 * gate because this repository has no deploy credentials or full Worker router fixture.
 */
describe("B2a real-contract publication release gate", () => {
  it("runs acceptance through projection persistence, snapshot export, merge, build, serve, and DOM", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
    const first = await admitAcceptedPublished(env, "variant-one", "a");
    const second = await admitAcceptedPublished(env, "variant-two", "b");
    const snapshot = await createAndExportSnapshot(env);
    const bundle = await materializeExportBundle(env, snapshot, "positive");
    const output = join(tempRoot, "positive-output");

    merge(bundle, output);

    // Negative 1: the production merge rejects a truncated production export.
    const truncated = cloneBundle(bundle, "truncated");
    const truncatedSnapshot = JSON.parse(readFileSync(join(truncated, "snapshot.json"), "utf-8"));
    truncatedSnapshot.rows.pop();
    writeFileSync(join(truncated, "snapshot.json"), JSON.stringify(truncatedSnapshot));
    expect(() => merge(truncated, join(tempRoot, "truncated-output"))).toThrow(/snapshot truncation/);

    // Negative 2: the content-addressed R2 write contract rejects post-reference overwrite.
    await expect(persistProjectionCreateOnly(env, first.projectionObjectSha, "mutated projection bytes"))
      .rejects.toThrow(/collision or mutation/);

    // Negative 3: the live model-page data contract rejects community rank leakage.
    installCommunityOutput(output);
    const groupPath = join(communityDir, "groups", `${SUFFIX}.json`);
    const leaked = JSON.parse(readFileSync(groupPath, "utf-8"));
    leaked.ranked = true;
    leaked.variants[0].ranked = true;
    writeFileSync(groupPath, JSON.stringify(leaked));
    await expect(getCommunityGroup(SUFFIX)).rejects.toThrow();
    installCommunityOutput(output);

    // Negative 4: the production merge rejects namespace collision with the protected catalog.
    const collisionCatalog = join(tempRoot, "collision-catalog.json");
    const catalog = JSON.parse(readFileSync(join(process.cwd(), "model_catalog.json"), "utf-8"));
    const models = Array.isArray(catalog) ? catalog : catalog.models;
    models.push({ id: TEST_COMMUNITY_GROUP_ID, slug: "collision" });
    writeFileSync(collisionCatalog, JSON.stringify(catalog));
    expect(() => merge(bundle, join(tempRoot, "collision-output"), collisionCatalog)).toThrow(/catalog\/group-id collision/);

    const activation = await activate(env, snapshot);
    expect(activation.status).toBe(200);
    const servedSnapshot = await handleServeActivePublicationSnapshot(getRequest("/api/publication-snapshot"), env);
    expect(servedSnapshot.status).toBe(200);
    expect((await servedSnapshot.json()).snapshot_id).toBe(snapshot.snapshot_id);

    const nextBin = join(process.cwd(), "node_modules", "next", "dist", "bin", "next");
    execFileSync(process.execPath, [nextBin, "build"], {
      cwd: process.cwd(), env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "pipe", timeout: 90_000,
    });
    const port = 31_000 + Math.floor(Math.random() * 1_000);
    const server = spawn(process.execPath, [join(process.cwd(), "tests", "fixtures", "static-server.mjs"), join(process.cwd(), "out"), String(port)], {
      cwd: process.cwd(), env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "pipe",
    });
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      await page.goto(`http://127.0.0.1:${port}/community/model/${SUFFIX}`, { waitUntil: "domcontentloaded" });
      expect(await page.locator("main").textContent()).toContain("community-declared, identity-unverified");
      expect(await page.locator("article").count()).toBe(2);
      const articleText = await page.locator("article").allTextContents();
      expect(articleText.join(" ")).toContain("variant-one");
      expect(articleText.join(" ")).toContain("variant-two");
      expect(articleText.every((value) => value.includes("unranked"))).toBe(true);
      expect(first.artifactSha).not.toBe(second.artifactSha);
    } finally {
      await browser.close();
      server.kill();
    }
  }, 120_000);

  it("fails activation when suppression lands after build materialization", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
    const accepted = await admitAcceptedPublished(env, "suppressed-variant", "c");
    const snapshot = await createAndExportSnapshot(env);
    const bundle = await materializeExportBundle(env, snapshot, "suppressed");
    merge(bundle, join(tempRoot, "suppressed-output"));

    // Negative 5: this is the build-to-activation race, through the real suppression CAS.
    await transitionAcceptedToTerminal(env, accepted.submissionId, "suppressed", "A9 mutation");
    const activation = await activate(env, snapshot);
    expect(activation.status).toBe(409);
    expect(await activation.json()).toMatchObject({ code: "publication_revision_mismatch" });
  });
});

async function admitAcceptedPublished(
  env: Awaited<ReturnType<typeof createEnv>>,
  displayName: string,
  artifactHex: string,
): Promise<{ artifactSha: string; projectionObjectSha: string; submissionId: string }> {
  const key = testKeyPair();
  const artifactSha = artifactHex.repeat(64);
  const bundleBytes = JSON.stringify(signedResultBundle(key, { compat_variant: displayName }, artifactSha));
  const rawSha = sha256Hex(bundleBytes);
  const ticketResponse = await issueTicket({
    env,
    request: jsonRequest("/api/submissions/tickets", communityTicketBody(rawSha, key), { "cf-connecting-ip": "203.0.113.9" }),
  });
  expect(ticketResponse.status).toBe(201);
  const ticket = await ticketResponse.json() as IssuedEnvelope;
  const targetResponse = await requestUpload({
    env,
    request: jsonRequest("/api/submissions/request-upload", {
      raw_bundle_sha256: rawSha, ticket_id: ticket.ticket_id, upload_capability: ticket.upload_capability,
    }, { "cf-connecting-ip": "203.0.113.9" }),
  });
  expect(targetResponse.status).toBe(200);
  const target = await targetResponse.json() as { r2_key: string; upload_headers: Record<string, string> };
  expect(target.upload_headers).toEqual({ "if-none-match": "*" });
  expect(await env.SUBMISSIONS.get(target.r2_key)).toBeNull();
  await env.SUBMISSIONS.put(target.r2_key, bundleBytes, { onlyIf: { etagDoesNotMatch: "*" } });
  const complete = await completeSubmission({
    env, params: { submissionId: ticket.ticket_id },
    request: jsonRequest(`/api/submissions/${ticket.ticket_id}/complete`, { raw_bundle_sha256: rawSha, size_bytes: bundleBytes.length }),
  });
  expect(complete.status).toBe(200);
  expect(await complete.json()).toMatchObject({ status: "pending_verification" });

  const update: any = statusUpdate("accepted", rawSha, "community");
  update.projection.model.display_name = displayName;
  update.projection.model.declared_name = displayName;
  update.projection.model.file_sha256 = artifactSha;
  update.projection.model.model_system_key = `artifact:${artifactSha}`;
  rehashStatusUpdate(update);
  const verification = await applyVerification({
    env, params: { submissionId: ticket.ticket_id },
    request: jsonRequest(`/api/admin/submissions/${ticket.ticket_id}/verification`, update, { "x-localbench-admin-secret": ADMIN_SECRET }),
  });
  expect(verification.status).toBe(200);
  const decision = await applyDecision({
    env, params: { submissionId: ticket.ticket_id },
    request: jsonRequest(`/api/admin/submissions/${ticket.ticket_id}/decision`, { publish_state: "published" }, { "x-localbench-admin-secret": ADMIN_SECRET }),
  });
  expect(decision.status).toBe(200);
  return { artifactSha, projectionObjectSha: update.projection_object_sha256, submissionId: ticket.ticket_id };
}

async function createAndExportSnapshot(env: Awaited<ReturnType<typeof createEnv>>): Promise<any> {
  const created = await handleCreatePublicationSnapshot(
    jsonRequest("/api/admin/publication-snapshot", {}, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
  );
  expect(created.status).toBe(201);
  const header: any = await created.json();
  const exported = await handleExportPublicationSnapshot(
    getRequest(`/api/admin/publication-snapshot?snapshot_id=${header.snapshot_id}&cursor=0`, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
  );
  expect(exported.status).toBe(200);
  return exported.json();
}

async function materializeExportBundle(
  env: Awaited<ReturnType<typeof createEnv>>,
  snapshot: any,
  label: string,
): Promise<string> {
  const bundle = join(tempRoot, `${label}-bundle`);
  const projections = join(bundle, "projections");
  mkdirSync(projections, { recursive: true });
  writeFileSync(join(bundle, "snapshot.json"), canonicalJson(snapshot));
  for (const row of snapshot.rows) {
    const object = await env.SUBMISSIONS.get(row.projection_r2_key);
    if (object === null) throw new Error(`missing exported projection ${row.projection_r2_key}`);
    writeFileSync(join(projections, `${row.projection_object_sha256}.json`), await new Response(object.body).text());
  }
  return bundle;
}

function merge(bundle: string, output: string, catalog = join(process.cwd(), "model_catalog.json")): void {
  mkdirSync(output, { recursive: true });
  const script = [
    "from pathlib import Path", "from publication_merge import merge_publication_bundle",
    "import sys", "merge_publication_bundle(Path(sys.argv[1]), Path(sys.argv[2]), catalog_path=Path(sys.argv[3]), board_path=Path(sys.argv[4]))",
  ].join("\n");
  execFileSync(process.env["LOCALBENCH_PYTHON"] ?? "python", ["-c", script, bundle, output, catalog, join(process.cwd(), "..", "cli", "runs", "board", "board_v2.json")], {
    cwd: process.cwd(), stdio: "pipe",
  });
}

function cloneBundle(bundle: string, label: string): string {
  const target = join(tempRoot, `${label}-bundle`);
  cpSync(bundle, target, { recursive: true });
  return target;
}

function installCommunityOutput(output: string): void {
  rmSync(communityDir, { force: true, recursive: true });
  cpSync(join(output, "community"), communityDir, { recursive: true });
}

function activate(env: Awaited<ReturnType<typeof createEnv>>, snapshot: any): Promise<Response> {
  return handleActivatePublicationSnapshot(
    jsonRequest("/api/admin/publication-snapshot?action=activate", {
      snapshot_id: snapshot.snapshot_id, publication_revision: snapshot.publication_revision,
    }, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
  );
}

function rehashStatusUpdate(update: any): void {
  const projection: any = update.projection;
  projection.artifact_hashes.projection_sha256 = "";
  projection.artifact_hashes.public_artifact_manifest_sha256 = "";
  const semantic = sha256Hex(canonicalJson(projection));
  projection.artifact_hashes.projection_sha256 = semantic;
  projection.artifact_hashes.public_artifact_manifest_sha256 = sha256Hex(canonicalJson({
    bundle_sha256: projection.artifact_hashes.bundle_sha256, projection_sha256: semantic,
  }));
  update.projection_sha256 = semantic;
  update.projection_object_sha256 = sha256Hex(canonicalJson(projection));
}
