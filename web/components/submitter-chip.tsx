type SubmitterChipProps = {
  readonly displayName: string | null | undefined;
  readonly emptyLabel: string;
  readonly githubLogin: string | null | undefined;
  readonly keyFingerprint: string | null | undefined;
  readonly prefix?: string;
};

export function SubmitterChip({
  displayName,
  emptyLabel,
  githubLogin,
  keyFingerprint,
  prefix = "",
}: SubmitterChipProps) {
  const primary = githubLogin !== null && githubLogin !== undefined
    ? `@${githubLogin}`
    : displayName ?? (keyFingerprint ? `key:${keyFingerprint}` : emptyLabel);
  const secondary = githubLogin !== null && githubLogin !== undefined ? displayName : null;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1 rounded border border-bench-line px-1.5 py-0.5 font-mono text-[10px] text-bench-muted">
      <span>{prefix}{primary}</span>
      {secondary === null || secondary === undefined ? null : <span>· {secondary}</span>}
    </span>
  );
}
