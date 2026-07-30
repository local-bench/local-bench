import { AcceptedResultProjectionV2Schema } from "./submission-contracts";
import type { PublicExecutionProfile } from "../../lib/execution-profile";

const PUBLIC_PROVENANCE_NOTE_LIMIT = 16;
const PUBLIC_TEXT_CODE_POINT_LIMIT = 300;
const UNSAFE_PUBLIC_TEXT_RE = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]+/gu;

type AcceptedProjection = ReturnType<typeof AcceptedResultProjectionV2Schema.parse>;

export function publicProvenanceNotes(
  notes: readonly string[],
  executionProfile?: PublicExecutionProfile,
): readonly string[] {
  const normalized = notes
    .filter((note) => !note.startsWith("execution_profile:"))
    .map(publicText);
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
  const profileNote = executionProfile === undefined
    ? undefined
    : `execution_profile:${executionProfile.id}`;
  const contentLimit = profileNote === undefined
    ? PUBLIC_PROVENANCE_NOTE_LIMIT
    : PUBLIC_PROVENANCE_NOTE_LIMIT - 1;
  if (collapsed.length <= contentLimit) {
    return profileNote === undefined ? collapsed : [...collapsed, profileNote];
  }
  const visible = collapsed.slice(0, contentLimit - 1);
  const truncated = [...visible, `+${collapsed.length - visible.length} more`];
  return profileNote === undefined ? truncated : [...truncated, profileNote];
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
