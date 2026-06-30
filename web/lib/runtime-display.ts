export type RuntimeDisplayInput = {
  readonly name?: string | null | undefined;
  readonly version?: string | null | undefined;
};

export type RuntimeDisplay = {
  readonly label: string;
  readonly version: string | null;
};

export function runtimeDisplay(runtime: RuntimeDisplayInput | null | undefined): RuntimeDisplay | null {
  const name = cleanRuntimePart(runtime?.name);
  const version = shortRuntimeVersion(runtime?.version);
  if (name === null && version === null) {
    return null;
  }
  return { label: name ?? "unknown", version };
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
