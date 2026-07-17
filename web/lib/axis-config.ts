export type AxisConfigEntry = { readonly key: string; readonly label: string; readonly color: string };

// Order here is the canonical DISPLAY order across the site. Colors are the one axis palette
// used everywhere an axis is drawn (index contribution rails, per-axis mini bars, header dots) —
// inline hex, not Tailwind classes, because lib/ is outside the Tailwind content globs (same
// precedent as family-color.ts). Hues come from the theme: accent/reasoning-edge/purple/warn/
// better/magenta.
export const AXIS_CONFIG = [
  { key: "agentic", label: "Agentic", color: "#3fd0d4" },
  { key: "knowledge", label: "Knowledge", color: "#7c9fff" },
  { key: "instruction", label: "Instruction", color: "#b388ff" },
  { key: "tool_calling", label: "Tool calling", color: "#ffb627" },
  // Coding is magenta, NOT the theme's mint green — mint sits too close to the agentic cyan
  // to tell the two biggest segments apart (owner call, 2026-07-05).
  { key: "coding", label: "Coding", color: "#ff5fa8" },
  { key: "math", label: "Math", color: "#36e0b0" },
] as const satisfies readonly AxisConfigEntry[];

// Accent at ~55% — the historical mini-bar fill, kept for axes outside the canonical set.
const DEFAULT_AXIS_COLOR = "#3fd0d48c";

const COLORS: ReadonlyMap<string, string> = new Map([
  ...AXIS_CONFIG.map((axis) => [axis.key, axis.color] as const),
  ["tool_use", "#ffb627"],
]);

export function axisColor(key: string | undefined): string {
  return (key === undefined ? undefined : COLORS.get(key)) ?? DEFAULT_AXIS_COLOR;
}

export type AxisKey = (typeof AXIS_CONFIG)[number]["key"];

export const AXIS_KEYS: readonly AxisKey[] = AXIS_CONFIG.map((axis) => axis.key);

const LABELS: ReadonlyMap<string, string> = new Map(AXIS_CONFIG.map((axis) => [axis.key, axis.label]));

export function isAxisKey(key: string): boolean {
  return LABELS.has(key);
}

export function axisLabel(key: string): string {
  // Season-2 macro-axis: structural key stays "tool_use", display label is
  // "Agentic" (index-v4.1 rename). The season-1 "agentic" key in AXIS_CONFIG
  // keeps the same word for its historical AppWorld-only axis; the two keys
  // never render in the same table (axis lists branch on season).
  if (key === "tool_use") return "Agentic";
  return LABELS.get(key) ?? key.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function presentAxes<T>(axes: Record<string, T>): readonly (readonly [string, T])[] {
  const entries: [string, T][] = [];
  for (const config of AXIS_CONFIG) {
    const value = axes[config.key];
    if (value !== undefined) {
      entries.push([config.key, value]);
    }
  }
  const extra = Object.keys(axes)
    .filter((key) => !isAxisKey(key))
    .sort();
  for (const key of extra) {
    const value = axes[key];
    if (value !== undefined) {
      entries.push([key, value]);
    }
  }
  return entries;
}
