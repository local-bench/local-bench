import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { BenchmarkOnramp } from "../components/benchmark-onramp";
import {
  SortableHeader,
  nextSort,
} from "../components/leaderboard-table-cells";
import { shouldNavigateCommunityRow } from "../components/community-leaderboard-row";

class RowClickTarget extends EventTarget {
  public constructor(private readonly interactive: boolean) {
    super();
  }

  public closest(): object | null {
    return this.interactive ? {} : null;
  }
}

describe("accessibility interaction state", () => {
  it("exposes sortable header state through each direction transition", () => {
    const onSort = vi.fn();
    const descending = { key: "composite", direction: "desc" } as const;
    const ascending = nextSort(descending, "composite");
    const inactive = renderToStaticMarkup(
      <table><thead><tr><SortableHeader label="Model" sortKey="model" sort={descending} onSort={onSort} /></tr></thead></table>,
    );

    expect(renderHeader(descending, onSort)).toContain('aria-sort="descending"');
    expect(renderHeader(ascending, onSort)).toContain('aria-sort="ascending"');
    expect(inactive).toContain('aria-sort="none"');
  });

  it("exposes the active onramp mode as pressed", () => {
    const html = renderToStaticMarkup(<BenchmarkOnramp benchmarkedModels={[]} catalog={[]} popularityAsOf={null} />);

    expect(html).toMatch(/aria-pressed="true"[^>]*>Popular<\/button>/u);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Browse catalog<\/button>/u);
  });

  it("keeps diagnostics controls in place while row-background clicks navigate", () => {
    expect(shouldNavigateCommunityRow(new RowClickTarget(true))).toBe(false);
    expect(shouldNavigateCommunityRow(new RowClickTarget(false))).toBe(true);
  });
});

function renderHeader(
  sort: { readonly key: string; readonly direction: "asc" | "desc" },
  onSort: (sort: { readonly key: string; readonly direction: "asc" | "desc" }) => void,
): string {
  return renderToStaticMarkup(
    <table><thead><tr><SortableHeader label="Score" sortKey="composite" sort={sort} onSort={onSort} /></tr></thead></table>,
  );
}
