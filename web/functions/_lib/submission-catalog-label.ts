import modelCatalog from "../../model_catalog.json";

const catalogLabels = new Map(
  modelCatalog.models.map((model) => [model.slug, model.display_name] as const),
);

export function publicPendingModelLabel(declaredSlug: string | null, submissionId: string): string {
  if (declaredSlug !== null) {
    const canonical = catalogLabels.get(declaredSlug);
    if (canonical !== undefined) return canonical;
  }
  return `Pending submission · ${shortQueueId(submissionId)}`;
}

function shortQueueId(submissionId: string): string {
  const safe = submissionId.replace(/[^A-Za-z0-9]/g, "");
  return safe.length === 0 ? "unknown" : safe.slice(-8);
}
