export type RuntimeDisplayInput = {
  readonly build_flags?: string | null | undefined;
  readonly name?: string | null | undefined;
  readonly version?: string | null | undefined;
};

const LLAMA_CPP_BUILD_RE = /^b\d{4,6}\b/u;
const BUILD_FLAGS_COMMIT_RE = /\(([0-9a-f]{6,12})\)/u;

// Some llama.cpp builds self-report a meaningless version ("b1" from a source build)
// while the real commit id sits in build_flags ("version: 1 (38c66ad); built with...").
// Display-time repair only — stored data is never mutated (owner call, 2026-07-22).
function repairedRuntimeVersion(runtime: RuntimeDisplayInput | null | undefined): string | null | undefined {
  const version = runtime?.version;
  const name = runtime?.name?.trim().toLowerCase();
  const flags = runtime?.build_flags;
  if (name !== "llama.cpp" || typeof flags !== "string") return version;
  const cleaned = version?.trim() ?? "";
  if (cleaned !== "" && LLAMA_CPP_BUILD_RE.test(cleaned)) return version;
  const commit = BUILD_FLAGS_COMMIT_RE.exec(flags)?.[1];
  return commit ?? version;
}

export type RuntimeDisplay = {
  readonly label: string;
  readonly version: string | null;
};

export function runtimeDisplay(runtime: RuntimeDisplayInput | null | undefined): RuntimeDisplay | null {
  const name = cleanRuntimePart(runtime?.name);
  const version = shortRuntimeVersion(repairedRuntimeVersion(runtime));
  if (name === null && version === null) {
    return null;
  }
  return { label: canonicalRuntimeLabel(name) ?? "unknown", version };
}

function canonicalRuntimeLabel(name: string | null): string | null {
  return name?.toLowerCase() === "vllm" ? "vLLM" : name;
}

export function runtimeSortLabel(runtime: RuntimeDisplayInput | null | undefined): string {
  const display = runtimeDisplay(runtime);
  if (display === null) {
    return "";
  }
  return `${display.label} ${display.version ?? ""}`.trim().toLowerCase();
}

function shortRuntimeVersion(version: string | null | undefined): string | null {
  const cleaned = cleanRuntimePart(version);
  if (cleaned === null) {
    return null;
  }
  return cleaned.length > 16 ? `${cleaned.slice(0, 16)}...` : cleaned;
}

function cleanRuntimePart(value: string | null | undefined): string | null {
  const cleaned = value?.trim();
  return cleaned === undefined || cleaned === "" ? null : cleaned;
}
