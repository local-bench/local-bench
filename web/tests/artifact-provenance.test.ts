import { describe, expect, it } from "vitest";
import { resolveArtifactProvenance } from "../lib/artifact-provenance";

const CATALOG_SHA = "ffb9a0f8b459086f8befd964f6c0ed9f9caafba410b76f9688b91c4678cc0fe4";
const REGISTRY_SHA = "33625d8dc3a5dd8d88c324d47db58561b11f7072816287078bfe58b4c55782f9";

describe("resolveArtifactProvenance", () => {
  it("prefers an exact catalog sha match over the registry", () => {
    // Given the same sha in both sources with deliberately different publishers.
    const provenance = resolveArtifactProvenance(
      CATALOG_SHA,
      [catalogArtifact()],
      {
        [CATALOG_SHA]: registryEntry({ repo_id: "registry/wrong-source" }),
      },
    );

    // Then the catalog artifact is authoritative.
    expect(provenance).toMatchObject({
      filename: "Qwen3.6-27B-Q5_K_M.gguf",
      repo_id: "unsloth/Qwen3.6-27B-MTP-GGUF",
      revision: "5cb35eb3dcbf52dbce5f87dbc64df6aaffadcace",
    });
  });

  it("falls back to the registry for the sha-verified lmstudio artifact", () => {
    const provenance = resolveArtifactProvenance(
      REGISTRY_SHA,
      [],
      {
        [REGISTRY_SHA]: registryEntry(),
      },
    );

    expect(provenance).toMatchObject({
      filename: "Qwen3.6-27B-Q4_K_M.gguf",
      repo_id: "lmstudio-community/Qwen3.6-27B-GGUF",
      revision: "58c6607d9c4cae8b071b3781c73be633fb3dee36",
    });
  });

  it("does not infer provenance from an equal quant label when the sha differs", () => {
    // Given a Q4_K_M catalog artifact whose bytes are not the benchmarked bytes.
    const provenance = resolveArtifactProvenance(
      REGISTRY_SHA,
      [{
        ...catalogArtifact(),
        file_sha256: "a7cbd3ecc0e3f9b333edee61ae66bc87ed713c5d49587a8355814722ed329e0f",
        quant_label: "Q4_K_M",
      }],
      {},
    );

    // Then no publisher is claimed from the quant label alone.
    expect(provenance).toBeNull();
  });

  it("resolves an incoming community Q5_K_M row from its exact catalog sha", () => {
    const provenance = resolveArtifactProvenance(CATALOG_SHA, [catalogArtifact()], {});

    expect(provenance?.repo_id).toBe("unsloth/Qwen3.6-27B-MTP-GGUF");
  });
});

function catalogArtifact() {
  return {
    file_sha256: CATALOG_SHA,
    filename: "Qwen3.6-27B-Q5_K_M.gguf",
    quant_label: "Q5_K_M",
    repo_id: "unsloth/Qwen3.6-27B-MTP-GGUF",
    revision: "5cb35eb3dcbf52dbce5f87dbc64df6aaffadcace",
  };
}

function registryEntry(overrides: Readonly<Record<string, string>> = {}) {
  return {
    filename: "Qwen3.6-27B-Q4_K_M.gguf",
    repo_id: "lmstudio-community/Qwen3.6-27B-GGUF",
    revision: "58c6607d9c4cae8b071b3781c73be633fb3dee36",
    verified: "hf-lfs-oid",
    verified_at: "2026-07-26",
    ...overrides,
  };
}
