import type { ReactNode } from "react";
import type { ArtifactProvenance } from "@/lib/artifact-provenance";
import { huggingFaceRepoUrl } from "@/lib/community-links";

export function ArtifactProvenanceLine({
  provenance,
}: {
  readonly provenance: ArtifactProvenance | null | undefined;
}) {
  if (provenance === null || provenance === undefined) return null;
  const publisher = provenance.repo_id.split("/", 1)[0] ?? provenance.repo_id;
  return (
    <a
      className="w-fit font-mono text-[11px] text-bench-muted hover:text-bench-accent"
      href={huggingFaceRepoUrl(provenance.repo_id)}
      rel="noopener noreferrer"
      target="_blank"
      title={`${provenance.repo_id} @ ${provenance.revision.slice(0, 7)} — sha-verified artifact source`}
    >
      by {publisher}
    </a>
  );
}

export function VariantBadge({
  tone,
  title,
  children,
}: {
  readonly tone: "accent" | "anchor" | "better" | "mixed" | "muted";
  readonly title: string;
  readonly children: ReactNode;
}) {
  const className =
    tone === "better"
      ? "border-bench-better/45 bg-bench-better/10 text-bench-better"
      : tone === "mixed"
        ? "border-bench-mixed/45 bg-bench-mixed/10 text-bench-mixed"
        : tone === "anchor"
          ? "border-bench-anchor/45 bg-bench-anchor/10 text-bench-anchor"
          : tone === "muted"
            ? "border-bench-muted/40 bg-bench-muted/10 text-bench-muted"
            : "border-bench-accent/45 bg-bench-accent/10 text-bench-accent";
  return (
    <span
      className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${className}`}
      title={title}
    >
      {children}
    </span>
  );
}
