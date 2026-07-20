import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogShells } from "../components/catalog-shells";
import { IndexModelSchema } from "../lib/schemas";

describe("CatalogShells", () => {
  it("separates the empty-catalog summary from its submit call to action", () => {
    const model = IndexModelSchema.parse({
      axes: {},
      best_run_id: null,
      composite: null,
      demo: false,
      est_cost_usd: null,
      family: "Fixture",
      kind: "community",
      lane: null,
      model_label: "Fixture Model",
      n_runs: 0,
      ranked: false,
      replicated: false,
      score_status: "missing",
      slug: "fixture-model",
      tier: null,
      tokens_to_answer_median: null,
    });

    const html = renderToStaticMarkup(<CatalogShells models={[model]} />);

    expect(html).toContain("Not yet benchmarked — 1 catalog models on the roadmap");
    expect(html).toContain('href="/submit"');
    expect(html).toContain("be the first to submit a run →");
  });
});
