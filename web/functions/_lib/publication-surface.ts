export type PublicationLifecycleState = "hidden" | "preview" | "published" | "suppressed" | "withdrawn";

export type PublicationSurface = {
  readonly badge: "preview" | "published" | "suppressed" | "withdrawn" | null;
  readonly production: boolean;
  readonly previewDeploy: boolean;
};

import policy from "../../publication-surface-policy.json";

export const PUBLICATION_SURFACES = {
  hidden: publicationSurface(policy.hidden),
  preview: publicationSurface(policy.preview),
  published: publicationSurface(policy.published),
  suppressed: publicationSurface(policy.suppressed),
  withdrawn: publicationSurface(policy.withdrawn),
} satisfies Readonly<Record<PublicationLifecycleState, PublicationSurface>>;

function publicationSurface(value: { readonly badge: string | null; readonly previewDeploy: boolean; readonly production: boolean }): PublicationSurface {
  if (value.badge !== null && !["preview", "published", "suppressed", "withdrawn"].includes(value.badge)) {
    throw new Error(`invalid publication surface badge: ${value.badge}`);
  }
  return { ...value, badge: value.badge as PublicationSurface["badge"] };
}
