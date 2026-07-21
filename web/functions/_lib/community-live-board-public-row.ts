import { AcceptedResultProjectionV2Schema } from "./submission-contracts";

const PUBLIC_PROVENANCE_NOTE_LIMIT = 16;
const PUBLIC_TEXT_CODE_POINT_LIMIT = 300;
const UNSAFE_PUBLIC_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+/gu;

type AcceptedProjection = ReturnType<typeof AcceptedResultProjectionV2Schema.parse>;

export function publicProvenanceNotes(notes: readonly string[]): readonly string[] {
  const normalized = notes.map(publicText);
  const prefixCounts = new Map<string, number>();
  for (const note of normalized) {
    const prefix = collapsiblePrefix(note);
    if (prefix !== null) prefixCounts.set(prefix, (prefixCounts.get(prefix) ?? 0) + 1);
  }
  const collapsed: string[] = [];
  const emittedPrefixes = new Set<string>();
  for (const note of normalized) {
    const prefix = collapsiblePrefix(note);
    const count = prefix === null ? 0 : (prefixCounts.get(prefix) ?? 0);
    if (prefix === null || count < 2) {
      collapsed.push(note);
      continue;
    }
    if (emittedPrefixes.has(prefix)) continue;
    emittedPrefixes.add(prefix);
    collapsed.push(textWithSuffix(prefix, ` (${count} items)`));
  }
  if (collapsed.length <= PUBLIC_PROVENANCE_NOTE_LIMIT) return collapsed;
  const visible = collapsed.slice(0, PUBLIC_PROVENANCE_NOTE_LIMIT - 1);
  return [...visible, `+${collapsed.length - visible.length} more`];
}

export function publicRuntime(
  runtime: NonNullable<AcceptedProjection["runtime"]>,
): NonNullable<AcceptedProjection["runtime"]> {
  if (!("build_flags" in runtime) || runtime.build_flags === undefined || runtime.build_flags === null) return runtime;
  return { ...runtime, build_flags: publicText(runtime.build_flags) };
}

function collapsiblePrefix(note: string): string | null {
  const separator = note.indexOf("/");
  if (separator <= 0) return null;
  const prefix = note.slice(0, separator);
  return prefix.includes(":") && !prefix.endsWith(":") ? prefix : null;
}

function publicText(value: string): string {
  return [...value.replace(UNSAFE_PUBLIC_TEXT_RE, "; ")].slice(0, PUBLIC_TEXT_CODE_POINT_LIMIT).join("");
}

function textWithSuffix(value: string, suffix: string): string {
  const suffixCodePoints = [...suffix];
  const valueCodePoints = [...value].slice(0, PUBLIC_TEXT_CODE_POINT_LIMIT - suffixCodePoints.length);
  return [...valueCodePoints, ...suffixCodePoints].join("");
}
