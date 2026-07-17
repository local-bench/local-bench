import { AXIS_CONFIG, axisLabel } from "@/lib/axis-config";
import { formatScore } from "@/lib/format";
import { runtimeDisplay } from "@/lib/runtime-display";
import type { BoardEntryRow } from "@/lib/board-entry";

// Projection axis keys use the scoring-registry names; the site's display config uses "instruction"
// for the "instruction_following" axis. Map display key -> projection key when reading axis scores.
const PROJECTION_AXIS_ALIASES: Readonly<Record<string, string>> = {
  instruction: "instruction_following",
};

type ParsedAxis = {
  readonly score?: number | null;
  readonly n?: number;
  readonly status?: string;
};

function parseAxes(axisScoresJson: string): Readonly<Record<string, ParsedAxis>> {
  try {
    const parsed: unknown = JSON.parse(axisScoresJson);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, ParsedAxis>;
    }
  } catch {
    // fall through to empty
  }
  return {};
}

function axisValue(axes: Readonly<Record<string, ParsedAxis>>, displayKey: string): ParsedAxis | undefined {
  return axes[displayKey] ?? axes[PROJECTION_AXIS_ALIASES[displayKey] ?? displayKey];
}

function isMeasured(axis: ParsedAxis | undefined): boolean {
  return axis !== undefined && axis.status === "measured" && (axis.n ?? 0) > 0 && typeof axis.score === "number";
}

// Projection/board-entry scores are 0-1 (raw-accuracy scale); the rest of the board displays on a
// 0-100 scale (point = raw_accuracy * 100). Scale here so partial rows read consistently.
function scorePct(value: number): string {
  return formatScore(value * 100);
}

// Headline axes present (measured) in any row, in canonical display order.
function presentAxisColumns(rows: readonly BoardEntryRow[]): readonly string[] {
  const present = new Set<string>();
  for (const row of rows) {
    const axes = parseAxes(row.axis_scores_json);
    for (const config of AXIS_CONFIG) {
      if (isMeasured(axisValue(axes, config.key))) {
        present.add(config.key);
      }
    }
  }
  return AXIS_CONFIG.map((axis) => axis.key).filter((key) => present.has(key));
}

function PartialBadge({ children, title }: { readonly children: string; readonly title: string }) {
  return (
    <span
      className="inline-flex rounded border border-bench-muted/40 bg-bench-muted/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bench-muted"
      title={title}
    >
      {children}
    </span>
  );
}

export function PartialCoverageBoard({ rows }: { readonly rows: readonly BoardEntryRow[] }) {
  // The section exists for community submissions mid-profile; an empty shell with explainer
  // copy is clutter, so it renders nothing until the first partial row lands (owner call
  // 2026-07-09).
  if (rows.length === 0) {
    return null;
  }
  const axisKeys = presentAxisColumns(rows);
  return (
    <section
      data-testid="partial-coverage-board"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel"
    >
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Partial-coverage submissions</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Published runs that measured only part of the headline Index (for example the text+code profile, with the
          Agentic module not yet run). They are shown for transparency but are <span className="font-semibold text-bench-warn-soft">never globally ranked</span> and
          are not comparable to complete current-index rows. Each carries its coverage profile and the headline weight it covers.
        </p>
      </div>
      <div className="overflow-x-auto">
          <table data-testid="partial-coverage-table" className="min-w-[1140px] border-collapse text-sm">
            <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
              <tr>
                <th className="px-3 py-3 font-semibold">Rank</th>
                <th className="px-3 py-3 font-semibold">Model</th>
                <th className="px-3 py-3 font-semibold">Runtime</th>
                <th className="px-3 py-3 font-semibold">Coverage</th>
                <th className="px-3 py-3 font-semibold">Partial composite</th>
                {axisKeys.map((axis) => (
                  <th key={axis} className="px-3 py-3 font-semibold">
                    {axisLabel(axis)}
                  </th>
                ))}
                <th className="px-3 py-3 font-semibold">Trust</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const axes = parseAxes(row.axis_scores_json);
                const measuredPct = Math.round(row.measured_headline_weight * 100);
                return (
                  <tr
                    key={row.entry_id}
                    className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]"
                  >
                    <td className="px-3 py-3 font-mono text-bench-muted">—</td>
                    <td className="px-3 py-3">
                      <span className="font-mono font-semibold text-bench-text">
                        {row.model_display_name ?? "unknown"}
                      </span>
                      {row.model_quant_label === null ? null : (
                        <span className="ml-2 font-mono text-xs text-bench-muted">{row.model_quant_label}</span>
                      )}
                      {row.visibility === "preview" ? (
                        <span className="ml-2 align-middle">
                          <PartialBadge title="Preview row, not a finalized public result">preview</PartialBadge>
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-3">
                      <RuntimeCell row={row} />
                    </td>
                    <td className="px-3 py-3">
                      <span className="font-mono text-xs text-bench-text">{row.coverage_profile_id}</span>
                      <div className="mt-0.5 font-mono text-[10px] text-bench-muted">{measuredPct}% of headline weight</div>
                    </td>
                    <td className="px-3 py-3">
                      {row.index_version?.startsWith("index-v4.") === true && row.headline_complete === 0 ? (
                        <div>
                          <span className="font-mono text-xs text-bench-muted">season-1 anchor retained</span>
                          <div className="mt-0.5 text-[10px] text-bench-warn-soft">partial v4 composite withheld</div>
                        </div>
                      ) : row.partial_composite === null ? (
                        <span className="font-mono text-xs text-bench-muted">not measured</span>
                      ) : (
                        <div>
                          <span className="font-mono text-lg font-semibold text-bench-text">
                            {scorePct(row.partial_composite)}
                          </span>
                          <div className="mt-0.5 inline-flex items-center gap-2">
                            <PartialBadge title="No global rank: only part of the headline Index was measured">
                              unranked
                            </PartialBadge>
                            <span className="font-mono text-[10px] text-bench-muted">
                              headline contribution {scorePct(row.known_headline_contribution)}
                            </span>
                          </div>
                        </div>
                      )}
                    </td>
                    {axisKeys.map((axis) => {
                      const value = axisValue(axes, axis);
                      return (
                        <td key={axis} className="px-3 py-3 font-mono text-xs">
                          {isMeasured(value) ? (
                            <span className="text-bench-text">{scorePct(value?.score as number)}</span>
                          ) : (
                            <span className="text-bench-muted">n/a</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-3 py-3">
                      <span className="font-mono text-xs text-bench-text">{row.trust_label}</span>
                      <div className="mt-0.5 font-mono text-[10px] text-bench-muted">{row.verification_level}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
    </section>
  );
}

function RuntimeCell({ row }: { readonly row: BoardEntryRow }) {
  const display = runtimeDisplay({ name: row.runtime_name, version: row.runtime_version });
  if (display === null) {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return (
    <span className="flex min-w-[96px] flex-col gap-0.5 leading-tight">
      <span className="font-mono text-xs text-bench-text">{display.label}</span>
      {display.version === null ? null : (
        <span className="font-mono text-[10px] text-bench-muted">{display.version}</span>
      )}
    </span>
  );
}
