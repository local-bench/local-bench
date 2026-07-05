import { readFileSync } from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import SubmitPage from "../app/submit/page";

const REPO_ROOT = path.resolve(process.cwd(), "..");

function suiteResolverConstant(name: string): string {
  const source = readFileSync(path.join(REPO_ROOT, "cli", "src", "localbench", "suite_resolver.py"), "utf8");
  const match = new RegExp(`${name}: Final = "([^"]+)"`).exec(source);
  if (match === null) {
    throw new Error(`missing suite resolver constant ${name}`);
  }
  return match[1] ?? "";
}

describe("SubmitPage", () => {
  it("renders release guidance from the landed suite resolver constants", () => {
    const full = suiteResolverConstant("DEFAULT_SUITE_ID");
    const staticExec = suiteResolverConstant("STATIC_EXEC_SUITE_ID");
    const staticCore = suiteResolverConstant("STATIC_CORE_DIAG_SUITE_ID");
    const html = renderToStaticMarkup(createElement(SubmitPage));

    expect(html).toContain(full);
    expect(html).toContain(staticExec);
    expect(html).toContain(staticCore);
    expect(html).toContain("no submitter Docker requirement");
    expect(html).toContain("project re-execution");
    expect(html).toContain("local-bench.ai/submission?id=");
    expect(html).toContain("signed bundle");
    expect(html).toContain("Nothing auto-publishes");
  });
});
