import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
import { projectionKey } from "../functions/_lib/submission-storage";
import { transitionAcceptedToTerminal } from "../functions/_lib/submission-store";
import { getCommunityGroup } from "../lib/data";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { onRequestGet as exportProjection } from "../functions/api/admin/publication-projection";
import { communityTicketBody, signedResultBundle, testKeyPair } from "./submission-contract-v2-support";
import {
  ADMIN_SECRET, MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009,
  MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014, MIGRATION_0015, MIGRATION_0016, TEST_COMMUNITY_GROUP_ID, completeProjection, createEnv, getRequest, jsonRequest, sha256Hex,
  type IssuedEnvelope,
} from "./submission-test-support";

const SUFFIX = TEST_COMMUNITY_GROUP_ID.replace("community-group:", "");
const MIGRATIONS = [MIGRATION_0002, MIGRATION_0004, MIGRATION_0005, MIGRATION_0006, MIGRATION_0008, MIGRATION_0009, MIGRATION_0010, MIGRATION_0011, MIGRATION_0013, MIGRATION_0014, MIGRATION_0015, MIGRATION_0016];
const communityDir = join(process.cwd(), "public", "data", "community");
const tempRoot = mkdtempSync(join(tmpdir(), "b2a-blackbox-"));
let admissionSequence = 0;

// public/data/community holds COMMITTED publication data since 2026-07-18. The
// serve/DOM assertions still need fixture output installed at the real path, so
// snapshot the committed tree up front and restore it on teardown instead of
// deleting it (the old bare rmSync silently stripped the committed files from
// the working tree on every suite run).
const committedCommunityBackup = join(tempRoot, "committed-community-backup");
const hadCommittedCommunity = existsSync(communityDir);
if (hadCommittedCommunity) {
  cpSync(communityDir, committedCommunityBackup, { recursive: true });
}

afterAll(() => {
  rmSync(communityDir, { force: true, recursive: true });
  if (hadCommittedCommunity) {
    cpSync(committedCommunityBackup, communityDir, { recursive: true });
  }
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
    const accepted = [];
    for (let index = 0; index < 101; index += 1) {
      accepted.push(await admitAcceptedPublished(env, `variant-${String(index).padStart(3, "0")}`, `artifact-${index}`));
    }
    const snapshot = await createSnapshot(env);
    expect((await activate(env, snapshot)).status).toBe(200);
    const admin = await startAdminServer(env);
    try {
      const bundle = await exportBundleViaProductionExporter(admin.baseUrl, snapshot, "positive");
      const output = join(tempRoot, "positive-output");
      await merge(bundle, output, join(process.cwd(), "model_catalog.json"), admin.baseUrl);
      installCommunityOutput(output);
      await assertServeAndDom(env, 101);
      expect(admin.snapshotCursors).toContain(100);
      expect(new Set(accepted.map((item) => item.artifactSha)).size).toBe(101);
    } finally {
      await admin.close();
    }
  }, 600_000);

  it.each(["truncated-export", "projection-corruption", "referenced-overwrite", "rank-leakage", "catalog-collision"] as const)(
    "runs the complete release gate for negative mutation %s",
    async (mutation) => {
      const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
      const accepted = await admitAcceptedPublished(env, `negative-${mutation}`, "d");
      const snapshot = await createSnapshot(env);
      expect((await activate(env, snapshot)).status).toBe(200);
      const admin = await startAdminServer(env, mutation === "truncated-export" || mutation === "projection-corruption" ? mutation : undefined);
      try {
        if (mutation === "referenced-overwrite") {
          await env.SUBMISSIONS.put(projectionKey(accepted.projectionObjectSha), "mutated projection bytes");
        }
        await expect(runCompleteGate(env, snapshot, mutation, admin.baseUrl)).rejects.toThrow();
      } finally {
        await admin.close();
      }
    },
    120_000,
  );

  it("fails activation when suppression lands after build materialization", async () => {
    const env = await createEnv({ includeAdminSecret: true, includeR2Secrets: true, migrations: MIGRATIONS });
    const accepted = await admitAcceptedPublished(env, "suppressed-variant", "c");
    const snapshot = await createSnapshot(env);
    expect((await activate(env, snapshot)).status).toBe(200);
    const admin = await startAdminServer(env);
    try {
      const bundle = await exportBundleViaProductionExporter(admin.baseUrl, snapshot, "suppressed");
      await transitionAcceptedToTerminal(env, accepted.submissionId, "suppressed", "A9 mutation");
      await expect(merge(bundle, join(tempRoot, "suppressed-output"), join(process.cwd(), "model_catalog.json"), admin.baseUrl))
        .rejects.toThrow(/live active snapshot|live publication revision/);
    } finally {
      await admin.close();
    }
  });
});

async function admitAcceptedPublished(
  env: Awaited<ReturnType<typeof createEnv>>,
  displayName: string,
  artifactHex: string,
): Promise<{ artifactSha: string; projectionObjectSha: string; submissionId: string }> {
  const key = testKeyPair();
  const artifactSha = sha256Hex(artifactHex);
  const sourceOrdinal = admissionSequence++;
  const sourceIp = `198.51.${sourceOrdinal % 250}.${Math.floor(sourceOrdinal / 250) + 1}`;
  const bundleBytes = JSON.stringify(signedResultBundle(key, { compat_variant: displayName }, artifactSha));
  const rawSha = sha256Hex(bundleBytes);
  const ticketResponse = await issueTicket({
    env,
    request: jsonRequest("/api/submissions/tickets", communityTicketBody(rawSha, key), { "cf-connecting-ip": sourceIp }),
  });
  expect(ticketResponse.status).toBe(201);
  const ticket = await ticketResponse.json() as IssuedEnvelope;
  const targetResponse = await requestUpload({
    env,
    request: jsonRequest("/api/submissions/request-upload", {
      raw_bundle_sha256: rawSha, ticket_id: ticket.ticket_id, upload_capability: ticket.upload_capability,
    }, { "cf-connecting-ip": sourceIp }),
  });
  expect(targetResponse.status).toBe(200);
  const target = await targetResponse.json() as { r2_key: string; upload_headers: Record<string, string> };
  expect(target.upload_headers).toEqual({ "if-none-match": "*" });
  expect(await env.SUBMISSIONS.get(target.r2_key)).toBeNull();
  await env.SUBMISSIONS.put(target.r2_key, bundleBytes, { onlyIf: { etagDoesNotMatch: "*" } });
  const projection: any = completeProjection(rawSha, "community");
  projection.model.display_name = displayName;
  projection.model.declared_name = displayName;
  projection.model.file_sha256 = artifactSha;
  projection.model.model_system_key = `artifact:${artifactSha}`;
  rehashProjection(projection);
  const complete = await completeSubmission({
    env, params: { submissionId: ticket.ticket_id },
    request: jsonRequest(`/api/submissions/${ticket.ticket_id}/complete`, {
      accepted_result_projection: projection,
      raw_bundle_sha256: rawSha,
      size_bytes: bundleBytes.length,
    }),
  });
  expect(complete.status).toBe(200);
  expect(await complete.json()).toMatchObject({ status: "published" });
  return { artifactSha, projectionObjectSha: sha256Hex(canonicalJson(projection)), submissionId: ticket.ticket_id };
}

async function createSnapshot(env: Awaited<ReturnType<typeof createEnv>>): Promise<any> {
  const created = await handleCreatePublicationSnapshot(
    jsonRequest("/api/admin/publication-snapshot", {}, { "x-localbench-admin-secret": ADMIN_SECRET }), env,
  );
  expect(created.status).toBe(201);
  return created.json();
}

async function startAdminServer(
  env: Awaited<ReturnType<typeof createEnv>>,
  mutation?: "truncated-export" | "projection-corruption",
): Promise<{ baseUrl: string; close: () => Promise<void>; snapshotCursors: number[] }> {
  const snapshotCursors: number[] = [];
  const server = createServer(async (request, response) => {
    try {
      const url = `http://127.0.0.1:${(server.address() as { port: number }).port}${request.url ?? "/"}`;
      const webRequest = new Request(url, { headers: { "x-localbench-admin-secret": String(request.headers["x-localbench-admin-secret"] ?? "") } });
      let result = request.url?.startsWith("/api/admin/publication-projection")
        ? await exportProjection({ env, request: webRequest })
        : await handleExportPublicationSnapshot(webRequest, env);
      if (request.url?.startsWith("/api/admin/publication-snapshot")) {
        snapshotCursors.push(Number(new URL(url).searchParams.get("cursor") ?? "0"));
      }
      if (mutation === "truncated-export" && request.url?.startsWith("/api/admin/publication-snapshot") && result.ok) {
        const page = await result.json() as any; page.total_count += 1;
        result = new Response(JSON.stringify(page), { headers: { "content-type": "application/json" }, status: 200 });
      } else if (mutation === "projection-corruption" && request.url?.startsWith("/api/admin/publication-projection") && result.ok) {
        result = new Response(`${await result.text()} `, { headers: { "content-type": "application/json" }, status: 200 });
      }
      response.statusCode = result.status;
      result.headers.forEach((value, key) => response.setHeader(key, value));
      response.end(Buffer.from(await result.arrayBuffer()));
    } catch (error) {
      response.statusCode = 500; response.end(String(error));
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    snapshotCursors,
    close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  };
}

async function exportBundleViaProductionExporter(
  baseUrl: string,
  snapshot: any,
  label: string,
): Promise<string> {
  const bundle = join(tempRoot, `${label}-bundle`);
  const script = [
    "from pathlib import Path", "from publication_export import export_publication_bundle", "import sys",
    "export_publication_bundle(sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]))",
  ].join("\n");
  await new Promise<void>((resolve, reject) => {
    const child = spawn(process.env["LOCALBENCH_PYTHON"] ?? "python", ["-c", script, baseUrl, ADMIN_SECRET, snapshot.snapshot_id, bundle], {
      cwd: process.cwd(), stdio: "pipe",
    });
    let stderr = "";
    child.stderr.on("data", (chunk) => { stderr += String(chunk); });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve() : reject(new Error(`production exporter failed (${code}): ${stderr}`)));
  });
  expect(JSON.parse(readFileSync(join(bundle, "export-metadata.json"), "utf-8"))).toMatchObject({
    exporter: "web/publication_export.py", schema_version: "localbench.publication_export.v1",
  });
  return bundle;
}

async function merge(bundle: string, output: string, catalog: string, publicationBaseUrl: string): Promise<void> {
  mkdirSync(output, { recursive: true });
  const script = [
    "from pathlib import Path", "from publication_merge import merge_publication_bundle",
    "import sys", "merge_publication_bundle(Path(sys.argv[1]), Path(sys.argv[2]), catalog_path=Path(sys.argv[3]), board_path=Path(sys.argv[4]), publication_base_url=sys.argv[5], publication_admin_secret=sys.argv[6])",
  ].join("\n");
  await new Promise<void>((resolve, reject) => {
    const child = spawn(process.env["LOCALBENCH_PYTHON"] ?? "python", ["-c", script, bundle, output, catalog, join(process.cwd(), "..", "cli", "runs", "board", "board_v2.json"), publicationBaseUrl, ADMIN_SECRET], {
      cwd: process.cwd(), stdio: "pipe",
    });
    let stderr = "";
    child.stderr.on("data", (chunk) => { stderr += String(chunk); });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve() : reject(new Error(`production merge failed (${code}): ${stderr}`)));
  });
}

async function runCompleteGate(
  env: Awaited<ReturnType<typeof createEnv>>,
  snapshot: any,
  mutation: "truncated-export" | "projection-corruption" | "referenced-overwrite" | "rank-leakage" | "catalog-collision",
  publicationBaseUrl: string,
): Promise<void> {
  const label = `negative-${mutation}`;
  const bundle = await exportBundleViaProductionExporter(publicationBaseUrl, snapshot, label);
  let catalog = join(process.cwd(), "model_catalog.json");
  if (mutation === "catalog-collision") {
    catalog = join(tempRoot, `${label}-catalog.json`);
    const payload = JSON.parse(readFileSync(join(process.cwd(), "model_catalog.json"), "utf-8"));
    const models = Array.isArray(payload) ? payload : payload.models;
    models.push({ id: TEST_COMMUNITY_GROUP_ID, slug: "collision" });
    writeFileSync(catalog, JSON.stringify(payload));
  }
  const output = join(tempRoot, `${label}-output`);
  await merge(bundle, output, catalog, publicationBaseUrl);
  if (mutation === "rank-leakage") {
    const groupPath = join(output, "community", "groups", `${SUFFIX}.json`);
    const leaked = JSON.parse(readFileSync(groupPath, "utf-8"));
    leaked.ranked = true;
    leaked.variants[0].ranked = true;
    writeFileSync(groupPath, JSON.stringify(leaked));
  }
  installCommunityOutput(output);
  await assertServeAndDom(env, 1);
}

async function assertServeAndDom(env: Awaited<ReturnType<typeof createEnv>>, expectedVariants: number): Promise<void> {
  const servedSnapshot = await handleServeActivePublicationSnapshot(getRequest("/api/publication-snapshot"), env);
  expect(servedSnapshot.status).toBe(200);
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
    const group = await getCommunityGroup(SUFFIX);
    expect(group?.variants).toHaveLength(expectedVariants);
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/community/model/${SUFFIX}`, { waitUntil: "domcontentloaded" });
    expect(await page.locator("main").textContent()).toContain("community-declared, identity-unverified");
    expect(await page.locator("article").count()).toBe(expectedVariants);
    expect((await page.locator("article").allTextContents()).every((value) => value.includes("unranked"))).toBe(true);
  } finally {
    await browser.close();
    server.kill();
  }
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

function rehashProjection(projection: any): void {
  projection.artifact_hashes.projection_sha256 = "";
  projection.artifact_hashes.public_artifact_manifest_sha256 = "";
  const semantic = sha256Hex(canonicalJson(projection));
  projection.artifact_hashes.projection_sha256 = semantic;
  projection.artifact_hashes.public_artifact_manifest_sha256 = sha256Hex(canonicalJson({
    bundle_sha256: projection.artifact_hashes.bundle_sha256, projection_sha256: semantic,
  }));
}
