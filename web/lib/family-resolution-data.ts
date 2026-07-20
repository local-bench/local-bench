import modelCatalogJson from "../model_catalog.json";
import {
  buildFamilyResolutionContext,
  type FamilyResolutionContext,
  type FamilyResolutionIndexModel,
} from "./family-resolution";
import { overlayLineageByArtifactSha } from "./overlay-lineage";
import { CatalogSchema, type CatalogModel } from "./schemas";

const parsedCatalog = CatalogSchema.parse(modelCatalogJson);
const catalogModels: readonly CatalogModel[] = Array.isArray(parsedCatalog)
  ? parsedCatalog
  : parsedCatalog.models;

export function familyResolutionContext(
  indexModels: readonly FamilyResolutionIndexModel[] = [],
): FamilyResolutionContext {
  return buildFamilyResolutionContext(
    catalogModels,
    indexModels,
    overlayLineageByArtifactSha(),
  );
}
