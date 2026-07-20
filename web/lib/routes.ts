export function modelHref(slug: string): string {
  return `/model/${encodeURIComponent(slug)}/`;
}

export function runHref(runId: string): string {
  return `/run/${encodeURIComponent(runId)}/`;
}

export function familyHref(slug: string): string {
  return `/families/${encodeURIComponent(slug)}/`;
}
