export type AxisConfigEntry = { readonly key: string; readonly label: string };

// Order here is the canonical DISPLAY order across the site.
export const AXIS_CONFIG = [
  { key: "knowledge", label: "Knowledge" },
  { key: "instruction", label: "Instruction" },
  { key: "agentic", label: "Agentic" },
  { key: "math", label: "Math" },
] as const satisfies readonly AxisConfigEntry[];

export type AxisKey = (typeof AXIS_CONFIG)[number]["key"];

export const AXIS_KEYS: readonly AxisKey[] = AXIS_CONFIG.map((axis) => axis.key);

const LABELS: ReadonlyMap<string, string> = new Map(AXIS_CONFIG.map((axis) => [axis.key, axis.label]));

export function isAxisKey(key: string): boolean {
  return LABELS.has(key);
}

export function axisLabel(key: string): string {
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
