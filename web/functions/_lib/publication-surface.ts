export type PublicationLifecycleState = "hidden" | "preview" | "published" | "suppressed" | "withdrawn";

export type PublicationSurface = {
  readonly badge: "preview" | "published" | "suppressed" | "withdrawn" | null;
  readonly production: boolean;
  readonly previewDeploy: boolean;
};

export const PUBLICATION_SURFACES = policy satisfies Readonly<Record<PublicationLifecycleState, PublicationSurface>>;
import policy from "../../publication-surface-policy.json";
