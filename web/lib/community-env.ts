import type { AdaptedBoardRow } from "./board-adapter";
import type { CommunityEnvOverlayEntry } from "./overlay-env";

type Hardware = NonNullable<AdaptedBoardRow["hardware"]>;
type Perf = NonNullable<AdaptedBoardRow["perf"]>;

export type MaintainerEnvBackfill = {
  readonly hardware?: {
    readonly gpu_name?: true;
    readonly vram_gb?: true;
  };
  readonly perf?: {
    readonly decode_tps?: true;
    readonly latency_s_median?: true;
    readonly overall_tps?: true;
    readonly prefill_tps?: true;
    readonly tokens_to_answer_median?: true;
    readonly wall_time_seconds?: true;
  };
};

export type CommunityEnvironment = {
  readonly hardware?: Hardware | undefined;
  readonly maintainerEnvBackfill?: MaintainerEnvBackfill | undefined;
  readonly perf?: Perf | undefined;
};

export function mergeCommunityEnvironment(
  projection: CommunityEnvironment,
  baked: CommunityEnvironment | undefined,
  overlay: CommunityEnvOverlayEntry | undefined,
): CommunityEnvironment {
  const gpuName = selectField({
    baked: normalizeGpuName(baked?.hardware?.gpu_name),
    bakedBackfill: baked?.maintainerEnvBackfill?.hardware?.gpu_name === true,
    overlay: normalizeGpuName(overlay?.hardware.gpu_name),
    projection: normalizeGpuName(projection.hardware?.gpu_name),
  });
  const vramGb = selectField({
    baked: baked?.hardware?.vram_gb,
    bakedBackfill: baked?.maintainerEnvBackfill?.hardware?.vram_gb === true,
    overlay: overlay?.hardware.vram_gb,
    projection: projection.hardware?.vram_gb,
  });
  const decodeTps = selectField({
    baked: baked?.perf?.decode_tps,
    bakedBackfill: baked?.maintainerEnvBackfill?.perf?.decode_tps === true,
    overlay: overlay?.perf.decode_tps,
    projection: projection.perf?.decode_tps,
  });
  const latency = selectField({
    baked: baked?.perf?.latency_s_median,
    bakedBackfill: baked?.maintainerEnvBackfill?.perf?.latency_s_median === true,
    overlay: undefined,
    projection: projection.perf?.latency_s_median,
  });
  const tokens = selectField({
    baked: baked?.perf?.tokens_to_answer_median,
    bakedBackfill: baked?.maintainerEnvBackfill?.perf?.tokens_to_answer_median === true,
    overlay: overlay?.perf.tokens_to_answer_median,
    projection: projection.perf?.tokens_to_answer_median,
  });
  const prefillTps = selectField({
    baked: baked?.perf?.prefill_tps,
    bakedBackfill: baked?.maintainerEnvBackfill?.perf?.prefill_tps === true,
    overlay: overlay?.perf.prefill_tps,
    projection: projection.perf?.prefill_tps,
  });
  const overallTps = selectField({
    baked: baked?.perf?.overall_tps,
    bakedBackfill: baked?.maintainerEnvBackfill?.perf?.overall_tps === true,
    overlay: overlay?.perf.overall_tps,
    projection: projection.perf?.overall_tps,
  });
  const wallTimeOverride = overlay?.perf_overrides?.wall_time_seconds;
  const wallTime = wallTimeOverride !== undefined
    // Maintainer correction: the submitted value is known-wrong, the overlay wins.
    ? { backfilled: true, value: wallTimeOverride }
    : selectField({
      baked: baked?.perf?.wall_time_seconds,
      bakedBackfill: baked?.maintainerEnvBackfill?.perf?.wall_time_seconds === true,
      overlay: overlay?.perf.wall_time_seconds,
      projection: projection.perf?.wall_time_seconds,
    });
  const hardwareBackfill = {
    ...(gpuName.backfilled ? { gpu_name: true as const } : {}),
    ...(vramGb.backfilled ? { vram_gb: true as const } : {}),
  };
  const perfBackfill = {
    ...(decodeTps.backfilled ? { decode_tps: true as const } : {}),
    ...(latency.backfilled ? { latency_s_median: true as const } : {}),
    ...(overallTps.backfilled ? { overall_tps: true as const } : {}),
    ...(prefillTps.backfilled ? { prefill_tps: true as const } : {}),
    ...(tokens.backfilled ? { tokens_to_answer_median: true as const } : {}),
    ...(wallTime.backfilled ? { wall_time_seconds: true as const } : {}),
  };
  const hasHardware = projection.hardware !== undefined || baked?.hardware !== undefined || overlay !== undefined;
  const hasPerf = projection.perf !== undefined || baked?.perf !== undefined || overlay !== undefined;
  const hasHardwareBackfill = Object.keys(hardwareBackfill).length > 0;
  const hasPerfBackfill = Object.keys(perfBackfill).length > 0;

  return {
    ...(hasHardware ? { hardware: { gpu_name: gpuName.value, vram_gb: vramGb.value } } : {}),
    ...(hasHardwareBackfill || hasPerfBackfill ? {
      maintainerEnvBackfill: {
        ...(hasHardwareBackfill ? { hardware: hardwareBackfill } : {}),
        ...(hasPerfBackfill ? { perf: perfBackfill } : {}),
      },
    } : {}),
    ...(hasPerf ? {
      perf: {
        decode_tps: decodeTps.value,
        ...(latency.value === null ? {} : { latency_s_median: latency.value }),
        ...(overallTps.value === null ? {} : { overall_tps: overallTps.value }),
        ...(prefillTps.value === null ? {} : { prefill_tps: prefillTps.value }),
        tokens_to_answer_median: tokens.value,
        wall_time_seconds: wallTime.value,
      },
    } : {}),
  };
}

function normalizeGpuName(value: string | null | undefined): string | null | undefined {
  return value === "" ? undefined : value;
}

function selectField<T>({
  baked,
  bakedBackfill,
  overlay,
  projection,
}: {
  readonly baked: T | null | undefined;
  readonly bakedBackfill: boolean;
  readonly overlay: T | null | undefined;
  readonly projection: T | null | undefined;
}): { readonly backfilled: boolean; readonly value: T | null } {
  if (projection !== null && projection !== undefined) return { backfilled: false, value: projection };
  if (baked !== null && baked !== undefined) return { backfilled: bakedBackfill, value: baked };
  if (overlay !== null && overlay !== undefined) return { backfilled: true, value: overlay };
  return { backfilled: false, value: null };
}
