import { describe, expect, it } from "vitest";
import { PUBLICATION_SURFACES } from "../functions/_lib/publication-surface";

describe("publication state to surface matrix", () => {
  it("keeps hidden/terminal states off deploys and separates preview from production", () => {
    expect(PUBLICATION_SURFACES).toEqual({
      hidden: { badge: null, previewDeploy: false, production: false },
      preview: { badge: "preview", previewDeploy: true, production: false },
      published: { badge: "published", previewDeploy: true, production: true },
      suppressed: { badge: "suppressed", previewDeploy: false, production: false },
      withdrawn: { badge: "withdrawn", previewDeploy: false, production: false },
    });
  });
});
