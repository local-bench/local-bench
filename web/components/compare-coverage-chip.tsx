import type { CompareCoverage } from "@/lib/compare";

export function CompareCoverageChip({ coverage }: { readonly coverage: CompareCoverage }) {
  return (
    <span
      className={[
        "inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold uppercase",
        coverage === "full"
          ? "border-bench-better/45 bg-bench-better/10 text-bench-better"
          : "border-bench-warn/45 bg-bench-warn/10 text-bench-warn",
      ].join(" ")}
    >
      {compareCoverageLabel(coverage)}
    </span>
  );
}

export function compareCoverageLabel(coverage: CompareCoverage): string {
  switch (coverage) {
    case "full":
      return "full index";
    case "partial":
      return "partial · renormalized · not rank-comparable";
    default:
      return assertNever(coverage);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled compare coverage: ${String(value)}`);
}
