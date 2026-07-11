export type PublicationLifecycleState = "hidden" | "preview" | "published" | "suppressed" | "withdrawn";

export type PublicationSurface = {
  readonly badge: "preview" | "published" | "suppressed" | "withdrawn" | null;
  readonly production: boolean;
  readonly previewDeploy: boolean;
};

export const PUBLICATION_SURFACES: Readonly<Record<PublicationLifecycleState, PublicationSurface>> = {
  hidden: { badge: null, previewDeploy: false, production: false },
  preview: { badge: "preview", previewDeploy: true, production: false },
  published: { badge: "published", previewDeploy: true, production: true },
  suppressed: { badge: "suppressed", previewDeploy: false, production: false },
  withdrawn: { badge: "withdrawn", previewDeploy: false, production: false },
};
