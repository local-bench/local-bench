#!/usr/bin/env node
// Local run:
//   npm install --prefix scripts/site-smoke
//   node scripts/site-smoke/check-live-surfaces.mjs
// Override production with: SITE_BASE_URL=http://localhost:3000 node scripts/site-smoke/check-live-surfaces.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium, request } from "playwright";

const BASE_URL = new URL(process.env.SITE_BASE_URL ?? "https://local-bench.ai");

// The repo's model catalog is the same source the site's artifact sha-join uses;
// reading it from the checkout lets the smoke resolve a live row's canonical
// display name and fine-tune status without depending on a served endpoint.
function repoModelCatalog() {
  try {
    const path = fileURLToPath(new URL("../../web/model_catalog.json", import.meta.url));
    const value = JSON.parse(readFileSync(path, "utf8"));
    return Array.isArray(value?.models) ? value.models : Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

const REPO_CATALOG = repoModelCatalog();

function catalogEntryForRow(row) {
  const sha = row?.model?.file_sha256;
  if (typeof sha !== "string") return undefined;
  return REPO_CATALOG.find((entry) => Array.isArray(entry?.quants)
    && entry.quants.some((quant) => quant?.file_sha256 === sha));
}

// Every name a surface may legitimately render for this row: the declared envelope
// name plus the catalog display name when the artifact sha resolves.
function acceptedNames(row) {
  const names = [displayName(row)];
  const entry = catalogEntryForRow(row);
  if (typeof entry?.display_name === "string" && !names.includes(entry.display_name)) {
    names.push(entry.display_name);
  }
  return names;
}

// Fine-tunes collapse under their base family on the landing board (owner call,
// 2026-07-22) — their own row must NOT appear there; they live on family/model pages.
function collapsesUnderBaseFamily(row) {
  return catalogEntryForRow(row)?.model_kind === "finetune";
}

async function firstVisibleNameRow(page, names, scope) {
  for (const candidate of names) {
    const locator = (scope ?? page).getByText(candidate, { exact: true });
    if (await locator.count() > 0) {
      return { locator: locator.first(), name: candidate };
    }
  }
  return null;
}
const NAVIGATION_TIMEOUT_MS = 30_000;
const HYDRATION_TIMEOUT_MS = 20_000;
const checks = [];

function record(invariant, check, passed, detail) {
  checks.push({ check, detail, invariant, passed });
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function displayName(row) {
  return row?.model?.display_name;
}

function parseEnvelope(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("API response is not a JSON object");
  }
  if (!Array.isArray(value.rows)) throw new Error("API response rows is not an array");
  if (!Number.isInteger(value.omitted_rows) || value.omitted_rows < 0) {
    throw new Error("API response omitted_rows is not a non-negative integer");
  }
  const rows = value.rows.map((row, index) => {
    const name = displayName(row);
    if (typeof row?.submission_id !== "string" || row.submission_id.length === 0) {
      throw new Error(`API row ${index} has no submission_id`);
    }
    if (typeof name !== "string" || name.length === 0) {
      throw new Error(`API row ${index} has no model.display_name`);
    }
    return row;
  });
  return { omittedRows: value.omitted_rows, rows };
}

function catalogDetailUrl(row, models) {
  const baseModels = Array.isArray(row.lineage?.base_model) ? row.lineage.base_model : [];
  const normalizedName = displayName(row).toLowerCase().replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "");
  const model = models.find((candidate) => baseModels.includes(candidate.catalog_id))
    ?? models.find((candidate) => candidate.slug === normalizedName);
  return typeof model?.slug === "string" ? new URL(`/model/${encodeURIComponent(model.slug)}/`, BASE_URL).toString() : null;
}

function isPopulatedScore(value) {
  const text = value.replace(/\s+/gu, " ").trim().toLowerCase();
  return text.length > 0 && !["—", "-", "n/a", "not measured", "no data"].includes(text);
}

async function freshnessText(page, boardOnly = false) {
  const scope = boardOnly ? page.getByTestId("full-leaderboard") : page.locator("body");
  const freshness = scope.getByText(/^(?:live · updated .+|showing last published snapshot.*)$/iu).first();
  await freshness.waitFor({ state: "visible", timeout: HYDRATION_TIMEOUT_MS });
  return (await freshness.innerText()).replace(/\s+/gu, " ").trim();
}

async function rowHardwareIsVisible(rowLocator) {
  if (await rowLocator.count() !== 1) return false;
  return /\b\d+(?:\.\d+)?\s*GB\b/iu.test(await rowLocator.innerText());
}

async function run() {
  let apiContext;
  let browser;
  try {
    apiContext = await request.newContext({ baseURL: BASE_URL.toString() });
    const apiResponse = await apiContext.get("/api/board/community.json", {
      headers: { accept: "application/json" },
      timeout: NAVIGATION_TIMEOUT_MS,
    });
    if (!apiResponse.ok()) {
      throw new Error(`GET /api/board/community.json returned HTTP ${apiResponse.status()}`);
    }
    const envelope = parseEnvelope(await apiResponse.json());
    record("A", "API envelope", true, `${envelope.rows.length} rows; server omitted_rows=${envelope.omittedRows}`);
    record(
      "A",
      "server omitted rows",
      envelope.omittedRows === 0,
      envelope.omittedRows === 0
        ? "no published rows omitted"
        : `${envelope.omittedRows} published row${envelope.omittedRows === 1 ? "" : "s"} omitted by server`,
    );
    const catalogResponse = await apiContext.get("/data/index.json", { timeout: NAVIGATION_TIMEOUT_MS });
    const catalogValue = catalogResponse.ok() ? await catalogResponse.json() : null;
    const catalogModels = Array.isArray(catalogValue?.models) ? catalogValue.models : [];

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
    const homeResponse = await page.goto(BASE_URL.toString(), { waitUntil: "domcontentloaded" });
    if (homeResponse === null || !homeResponse.ok()) {
      throw new Error(`home page returned HTTP ${homeResponse?.status() ?? "unknown"}`);
    }

    const homeFreshness = await freshnessText(page, true);
    if (/showing last published snapshot/iu.test(homeFreshness)) {
      record("B", "browser live feed", false, `freshness line: ${homeFreshness}`);
    } else {
      const heldBackMatch = /(?:^| · )(\d+) rows? held back\b/iu.exec(homeFreshness);
      const browserHeldBack = heldBackMatch === null ? 0 : Number.parseInt(heldBackMatch[1], 10);
      const delta = browserHeldBack - envelope.omittedRows;
      if (delta === 0) {
        record("B", "browser held-back parity", true, `${browserHeldBack} held back matches server omitted_rows`);
      } else if (delta > 0) {
        record("B", "browser held-back parity", false, `${browserHeldBack} held back vs server ${envelope.omittedRows}; browser dropped ${delta} extra row${delta === 1 ? "" : "s"}`);
      } else {
        record("B", "browser held-back parity", false, `${browserHeldBack} held back vs server ${envelope.omittedRows}; mismatch ${delta}`);
      }
    }

    const resolvedRows = [];
    for (const row of envelope.rows) {
      const name = displayName(row);
      const names = acceptedNames(row);
      const board = page.getByTestId("full-leaderboard");
      const match = await firstVisibleNameRow(page, names, board);
      const homeRow = match === null ? null : match.locator.locator("xpath=ancestor::tr[1]");
      const rowCount = homeRow === null ? 0 : await homeRow.count();
      if (collapsesUnderBaseFamily(row)) {
        record(
          "C",
          `home leaderboard: ${name}`,
          rowCount === 0,
          rowCount === 0
            ? "fine-tune collapses under its base family row (by design)"
            : `fine-tune must not have its own landing row; found ${rowCount} (${match?.name})`,
        );
      } else {
        record(
          "C",
          `home leaderboard: ${name}`,
          rowCount === 1,
          rowCount === 1
            ? `display name "${match?.name}" is visible after hydration`
            : `expected one row with an accepted display name (${names.join(" | ")}); found ${rowCount}`,
        );
      }
      let href = homeRow !== null && rowCount === 1 ? await homeRow.getAttribute("data-href") : null;
      if (href === null && homeRow !== null && rowCount === 1) {
        const anchor = homeRow.getByRole("link", { name: match?.name ?? name, exact: true }).first();
        if (await anchor.count() > 0) href = await anchor.getAttribute("href");
      }
      resolvedRows.push({
        envelopeRow: row,
        detailUrl: href === null ? catalogDetailUrl(row, catalogModels) : new URL(href, BASE_URL).toString(),
        needsScatter: typeof row.hardware?.vram_gb === "number"
          || (homeRow !== null && rowCount === 1 && await rowHardwareIsVisible(homeRow)),
      });
    }

    await page.goto(new URL("/leaderboard/", BASE_URL).toString(), { waitUntil: "domcontentloaded" });
    await freshnessText(page, true);
    await page.getByRole("button", { name: "Show all variants" }).click();
    await page.getByRole("button", { name: "Show best per family" }).waitFor({ state: "visible" });
    for (const resolved of resolvedRows) {
      const allVariantsRow = page.getByTestId(`community-row-${resolved.envelopeRow.submission_id}`);
      if (await allVariantsRow.count() !== 1) continue;
      resolved.needsScatter ||= await rowHardwareIsVisible(allVariantsRow);
      if (resolved.detailUrl !== null) continue;
      const href = await allVariantsRow.getAttribute("data-href");
      let anchorHref = null;
      for (const candidate of acceptedNames(resolved.envelopeRow)) {
        const anchor = allVariantsRow.getByRole("link", { name: candidate, exact: true }).first();
        if (await anchor.count() > 0) { anchorHref = await anchor.getAttribute("href"); break; }
      }
      const resolvedHref = href ?? anchorHref;
      if (resolvedHref !== null) resolved.detailUrl = new URL(resolvedHref, BASE_URL).toString();
    }

    for (const resolved of resolvedRows) {
      const row = resolved.envelopeRow;
      const name = displayName(row);
      if (resolved.detailUrl === null) {
        record("D", `detail page: ${name}`, false, "no detail link in the hydrated home row");
        record("E", `variant board: ${name}`, false, "detail/base page could not be resolved");
        record("E", `axis cells: ${name}`, false, "detail/base page could not be resolved");
        record("E", `scatter point: ${name}`, !resolved.needsScatter, resolved.needsScatter ? "detail/base page could not be resolved" : "not required; no envelope or overlay VRAM");
        continue;
      }

      const detailResponse = await page.goto(resolved.detailUrl, { waitUntil: "domcontentloaded" });
      let detailNameVisible = false;
      let detailHydration = "hydration did not complete";
      try {
        detailHydration = await freshnessText(page);
        const detailMatch = await firstVisibleNameRow(page, acceptedNames(row));
        if (detailMatch === null) throw new Error("no accepted display name found on the detail page");
        await detailMatch.locator.waitFor({ state: "visible", timeout: HYDRATION_TIMEOUT_MS });
        detailNameVisible = true;
      } catch (error) {
        detailHydration = errorMessage(error);
      }
      const detailOk = detailResponse !== null && detailResponse.status() === 200 && detailNameVisible;
      record("D", `detail page: ${name}`, detailOk, detailOk ? `HTTP 200; display name rendered; ${detailHydration}` : `HTTP ${detailResponse?.status() ?? "unknown"}; ${detailHydration}`);

      const lineageLink = page.getByRole("link", { name: /^Fine-tune of /iu }).first();
      const lineageHref = await lineageLink.count() === 0 ? null : await lineageLink.getAttribute("href");
      const baseUrl = lineageHref === null ? resolved.detailUrl : new URL(lineageHref, BASE_URL).toString();
      if (baseUrl !== page.url()) {
        const baseResponse = await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
        if (baseResponse === null || baseResponse.status() !== 200) {
          record("E", `variant board: ${name}`, false, `base page ${baseUrl} returned HTTP ${baseResponse?.status() ?? "unknown"}`);
          record("E", `axis cells: ${name}`, false, "base page unavailable");
          record("E", `scatter point: ${name}`, !resolved.needsScatter, resolved.needsScatter ? "base page unavailable" : "not required; no envelope or overlay VRAM");
          continue;
        }
      }
      try {
        await freshnessText(page);
      } catch (error) {
        record("E", `base hydration: ${name}`, false, errorMessage(error));
      }

      const variantBoard = page.getByTestId("model-variant-board");
      const variantRow = variantBoard.getByTestId(`community-variant-${row.submission_id}`);
      const variantCount = await variantRow.count();
      let variantNameCount = 0;
      if (variantCount === 1) {
        for (const candidate of acceptedNames(row)) {
          variantNameCount = await variantRow.getByText(candidate, { exact: true }).count();
          if (variantNameCount > 0) break;
        }
      }
      record("E", `variant board: ${name}`, variantCount === 1 && variantNameCount > 0, variantCount === 1 && variantNameCount > 0 ? `row rendered on ${new URL(baseUrl).pathname}` : variantCount === 1 ? "row present but no accepted display name matched" : `expected one community variant row; found ${variantCount}`);

      const headers = await variantBoard.locator("thead th").allTextContents();
      const vramColumn = headers.findIndex((header) => /VRAM\s*@8k/iu.test(header));
      const cells = variantCount === 1 ? await variantRow.locator(":scope > td").allTextContents() : [];
      const axisCells = vramColumn > 3 ? cells.slice(3, vramColumn) : [];
      const populatedAxes = axisCells.filter(isPopulatedScore);
      if (row.headline_complete === true) {
        record("E", `axis cells: ${name}`, populatedAxes.length > 0, populatedAxes.length > 0 ? `${populatedAxes.length}/${axisCells.length} axis cells populated` : `${axisCells.length} axis cells inspected; all empty or placeholders`);
      } else {
        record("E", `axis cells: ${name}`, true, "not required; headline_complete=false");
      }

      if (!resolved.needsScatter) {
        record("E", `scatter point: ${name}`, true, "not required; no envelope or overlay VRAM");
      } else {
        // Live rows plot as "community" (anonymous submissions) or "project" (maintainer
        // runs, origin project_anchor) — associate by row identity, never by kind alone.
        const scatterMarkers = page.getByTestId("quality-vram-scatter").locator('svg [data-point-kind="community"], svg [data-point-kind="project"]');
        const markerMatches = await scatterMarkers.evaluateAll(
          (markers, expectedName) => markers.filter((marker) => {
            const point = marker.parentElement;
            const identities = [
              marker.getAttribute("aria-label"),
              point?.getAttribute("aria-label"),
              point?.querySelector(":scope > title")?.textContent,
            ];
            return identities.some((identity) => identity?.includes(expectedName) === true);
          }).length,
          name,
        );
        record("E", `scatter point: ${name}`, markerMatches > 0, markerMatches > 0 ? `${markerMatches} matching live-row SVG datapoint${markerMatches === 1 ? "" : "s"}` : "no matching data-point element inside the scatter SVG");
      }
    }
  } finally {
    await browser?.close();
    await apiContext?.dispose();
  }
}

try {
  await run();
} catch (error) {
  record("A-F", "smoke execution", false, errorMessage(error));
}

for (const check of checks) {
  console.log(`[${check.passed ? "PASS" : "FAIL"}] ${check.invariant} ${check.check} — ${check.detail}`);
}

const failures = checks.filter((check) => !check.passed);
if (failures.length === 0) {
  console.log(`OK site smoke: ${checks.length} checks passed against ${BASE_URL.origin}`);
} else {
  console.log(`FAIL site smoke: ${failures.length}/${checks.length} checks failed against ${BASE_URL.origin}`);
  console.log("Failure list:");
  for (const failure of failures) console.log(`- ${failure.invariant} ${failure.check}: ${failure.detail}`);
  process.exitCode = 1;
}
