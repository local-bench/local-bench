import { describe, expect, it } from "vitest";
import { mergeCommunityEnvironment } from "../lib/community-env";
import { envOverlayByArtifactSha } from "../lib/overlay-env";

const BONSAI_SHA = "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757";

describe("community environment overlay", () => {
  it("keeps projection values ahead of baked and overlay values", () => {
    const overlay = requiredBonsaiOverlay();

    const merged = mergeCommunityEnvironment(
      {
        hardware: { gpu_name: "Live GPU", vram_gb: 48 },
        perf: { decode_tps: 90, tokens_to_answer_median: 1024, wall_time_seconds: 3600 },
      },
      {
        hardware: { gpu_name: "Baked GPU", vram_gb: 24 },
        perf: { decode_tps: 80, tokens_to_answer_median: 2048, wall_time_seconds: 7200 },
      },
      overlay,
    );

    expect(merged).toEqual({
      hardware: { gpu_name: "Live GPU", vram_gb: 48 },
      perf: { decode_tps: 90, tokens_to_answer_median: 1024, wall_time_seconds: 3600 },
    });
  });

  it("uses baked values before filling only remaining cells from the overlay", () => {
    const overlay = requiredBonsaiOverlay();

    const merged = mergeCommunityEnvironment(
      {
        hardware: { gpu_name: "Live GPU", vram_gb: null },
        perf: { decode_tps: 90, tokens_to_answer_median: null, wall_time_seconds: null },
      },
      {
        perf: { decode_tps: 80, tokens_to_answer_median: 2048, wall_time_seconds: null },
      },
      overlay,
    );

    expect(merged).toEqual({
      hardware: { gpu_name: "Live GPU", vram_gb: 31.8 },
      maintainerEnvBackfill: {
        hardware: { vram_gb: true },
        perf: { wall_time_seconds: true },
      },
      perf: {
        decode_tps: 90,
        tokens_to_answer_median: 2048,
        wall_time_seconds: 61272.45902150008,
      },
    });
  });
});

function requiredBonsaiOverlay() {
  const overlay = envOverlayByArtifactSha().get(BONSAI_SHA);
  if (overlay === undefined) throw new Error("expected Bonsai environment overlay");
  return overlay;
}
