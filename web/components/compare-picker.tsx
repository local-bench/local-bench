"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { DemoBadge } from "@/components/badges";
import { CompareCoverageChip, compareCoverageLabel } from "@/components/compare-coverage-chip";
import {
  ModularAxisProfile,
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { axisLabel, formatCompactNumber, formatGb, formatScore } from "@/lib/format";
import { getAxisDeltas, type AxisDelta, type CompareConfig } from "@/lib/compare";
import type { FineTuneComparePreset } from "@/lib/vs-base";

export function ComparePicker({
  configs,
  initialLeftId,
  initialRightId,
  fineTunePresets,
}: {
  readonly configs: readonly CompareConfig[];
  readonly fineTunePresets: readonly FineTuneComparePreset[];
  readonly initialLeftId: string | null;
  readonly initialRightId: string | null;
}) {
  const defaultLeft = findConfig(configs, initialLeftId) ?? configs[0] ?? null;
  const defaultRight = findDefaultRight(configs, defaultLeft?.id ?? null, initialRightId);
  const [leftId, setLeftId] = useState(defaultLeft?.id ?? "");
  const [rightId, setRightId] = useState(defaultRight?.id ?? "");
  const left = findConfig(configs, leftId) ?? defaultLeft;
  const right = findConfig(configs, rightId) ?? defaultRight;
  const axisDeltas = useMemo(() => (left && right ? getAxisDeltas(left, right) : []), [left, right]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryLeft = params.get("left");
    const queryRight = params.get("right");
    const queryFineTune = params.get("finetune");
    const matchedLeft = findConfig(configs, queryLeft);
    const matchedRight = findConfig(configs, queryRight);
    if (matchedLeft !== null) {
      setLeftId(matchedLeft.id);
    }
    if (matchedRight !== null) {
      setRightId(matchedRight.id);
    }
    if (matchedLeft === null && matchedRight === null && queryFineTune !== null) {
      const preset = fineTunePresets.find((candidate) => candidate.slug === queryFineTune);
      const presetLeft = findConfig(configs, preset?.leftRunId ?? null);
      const presetRight = findConfig(configs, preset?.rightRunId ?? null);
      if (presetLeft !== null && presetRight !== null) {
        setLeftId(presetLeft.id);
        setRightId(presetRight.id);
      }
    }
  }, [configs, fineTunePresets]);

  if (left === null || right === null) {
    return (
      <div className="rounded border border-bench-warn/35 bg-bench-warn/10 p-4 text-sm text-bench-warn">
        No comparable model x quant configs are available yet.
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 md:grid-cols-2">
        <ConfigSelect id="left-config" label="Left config" value={leftId} configs={configs} onChange={setLeftId} />
        <ConfigSelect id="right-config" label="Right config" value={rightId} configs={configs} onChange={setRightId} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ConfigCard config={left} label="Left" linkLabel="Open left model" />
        <ConfigCard config={right} label="Right" linkLabel="Open right model" />
      </div>

      <section className="grid gap-3 md:grid-cols-3">
        <DeltaCard
          label={`${LOCAL_INTELLIGENCE_INDEX_NAME} delta`}
          note={`${LOCAL_INTELLIGENCE_INDEX_QUALIFIER}. ${LOCAL_INTELLIGENCE_INDEX_PROFILE} deltas appear below.`}
          value={formatSigned(left.composite.point - right.composite.point)}
        />
        <DeltaCard label="VRAM delta" value={formatVramDelta(left, right)} />
        <DeltaCard label="tok/s delta" value={formatNullableDelta(left.tokS, right.tokS)} />
      </section>

      <section className="overflow-x-auto rounded border border-bench-line bg-bench-panel-2/70">
        <table data-testid="compare-axis-deltas" className="min-w-[820px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
            <tr>
              <th className="px-3 py-3">Axis</th>
              <th className="px-3 py-3">Left</th>
              <th className="px-3 py-3">Right</th>
              <th className="px-3 py-3">Delta</th>
              <th className="px-3 py-3">Winner</th>
            </tr>
          </thead>
          <tbody>
            {axisDeltas.map((delta) => (
              <AxisDeltaRow key={delta.axis} delta={delta} left={left} right={right} />
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function ConfigSelect({
  configs,
  id,
  label,
  onChange,
  value,
}: {
  readonly configs: readonly CompareConfig[];
  readonly id: string;
  readonly label: string;
  readonly onChange: (value: string) => void;
  readonly value: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted" htmlFor={id}>
      {label}
      <select
        id={id}
        aria-label={label}
        className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent"
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      >
        {configs.map((config) => (
          <option key={config.id} value={config.id}>
            {configLabel(config)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ConfigCard({ config, label, linkLabel }: { readonly config: CompareConfig; readonly label: string; readonly linkLabel: string }) {
  return (
    <section className="rounded border border-bench-line bg-bench-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase text-bench-muted">{label}</p>
          <h2 className="mt-1 text-xl font-semibold text-bench-text">{config.modelLabel}</h2>
          <p className="mt-1 font-mono text-sm text-bench-accent">{config.quantLabel}</p>
        </div>
        {config.demo ? <DemoBadge /> : null}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Metric
          detail={<ModularAxisProfile axes={config.axes} className="block font-mono text-[11px] text-bench-muted" />}
          label={
            <span className="flex flex-col gap-0.5 leading-tight">
              <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
              <span className="font-mono text-[10px] normal-case text-bench-muted">{LOCAL_INTELLIGENCE_INDEX_QUALIFIER}</span>
            </span>
          }
          value={
            <span className="flex flex-wrap items-center gap-2">
              <span>{formatScore(config.composite.point)}</span>
              <CompareCoverageChip coverage={config.coverage} />
            </span>
          }
        />
        <Metric label="Effective VRAM" value={formatGb(config.vramEstimate?.effectiveRequiredGb)} />
        <Metric label="Fits" value={config.fitTierGb === null ? ">512 GB" : `${config.fitTierGb} GB`} />
        <Metric label="tok/s" value={formatCompactNumber(config.tokS)} />
      </dl>
      <Link href={`/model/${config.modelSlug}`} className="mt-4 inline-flex text-sm font-semibold text-bench-accent hover:underline">
        {linkLabel}
      </Link>
    </section>
  );
}

function Metric({
  detail,
  label,
  value,
}: {
  readonly detail?: ReactNode;
  readonly label: ReactNode;
  readonly value: ReactNode;
}) {
  return (
    <div className="rounded border border-bench-line bg-bench-panel-2/70 p-3">
      <dt className="text-xs uppercase text-bench-muted">{label}</dt>
      <dd className="mt-1 font-mono text-bench-text">{value}</dd>
      {detail === undefined ? null : <dd className="mt-1">{detail}</dd>}
    </div>
  );
}

function DeltaCard({ label, note, value }: { readonly label: string; readonly note?: string; readonly value: string }) {
  return (
    <div className="rounded border border-bench-line bg-bench-panel p-4">
      <p className="text-xs uppercase text-bench-muted">{label}</p>
      {note === undefined ? null : <p className="mt-1 text-xs leading-5 text-bench-muted">{note}</p>}
      <p className="mt-2 font-mono text-xl font-semibold text-bench-text">{value}</p>
    </div>
  );
}

function AxisDeltaRow({
  delta,
  left,
  right,
}: {
  readonly delta: AxisDelta;
  readonly left: CompareConfig;
  readonly right: CompareConfig;
}) {
  return (
    <tr className="border-t border-bench-line/75 hover:bg-white/[0.035]">
      <td className="px-3 py-3 text-bench-text">{axisLabel(delta.axis)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatScore(delta.leftScore.point)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatScore(delta.rightScore.point)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatSigned(delta.delta)}</td>
      <td className="px-3 py-3 text-bench-muted">{winnerLabel(delta, left, right)}</td>
    </tr>
  );
}

function findConfig(configs: readonly CompareConfig[], id: string | null): CompareConfig | null {
  return id === null ? null : configs.find((config) => config.id === id) ?? null;
}

function findDefaultRight(configs: readonly CompareConfig[], leftId: string | null, rightId: string | null): CompareConfig | null {
  return findConfig(configs, rightId) ?? configs.find((config) => config.id !== leftId) ?? configs[0] ?? null;
}

function configLabel(config: CompareConfig): string {
  const demo = config.demo ? " · demo" : "";
  return `${config.modelLabel} · ${config.quantLabel} · ${compareCoverageLabel(config.coverage)}${demo} · ${formatGb(config.vramEstimate?.effectiveRequiredGb)}`;
}

function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatScore(value)}`;
}

function formatNullableDelta(left: number | null, right: number | null): string {
  return left === null || right === null ? "n/a" : formatSigned(left - right);
}

function formatVramDelta(left: CompareConfig, right: CompareConfig): string {
  const leftGb = left.vramEstimate?.effectiveRequiredGb ?? null;
  const rightGb = right.vramEstimate?.effectiveRequiredGb ?? null;
  return leftGb === null || rightGb === null ? "n/a" : formatGb(leftGb - rightGb);
}

function winnerLabel(delta: AxisDelta, left: CompareConfig, right: CompareConfig): string {
  switch (delta.winner) {
    case "left":
      return `${left.modelLabel} ${left.quantLabel} wins`;
    case "right":
      return `${right.modelLabel} ${right.quantLabel} wins`;
    case "tie":
      return "Tie";
    default:
      return assertNever(delta.winner);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled compare value: ${String(value)}`);
}
