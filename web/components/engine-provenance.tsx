import type { ServingProvenance } from "@/lib/schemas";

export function EngineProvenance({ provenance }: { readonly provenance: ServingProvenance | undefined }) {
  if (provenance === undefined || provenance.runtime !== "vllm") return null;
  const snapshot = provenance.snapshot;
  const deterministic = provenance.determinism;
  const numerics = provenance.numerics;
  return (
    <div className="mt-4 rounded-md border border-bench-line bg-white/[0.025] p-3 text-sm leading-6 text-bench-muted">
      <div className="font-mono text-xs uppercase text-bench-muted">serving engine provenance</div>
      <p className="mt-1 font-mono text-bench-text">
        {provenance.runtime} {provenance.engine_version ?? "version n/a"}
      </p>
      {provenance.engine_executable_sha256 === null ? null : <p className="mt-1 break-all font-mono text-xs">engine executable: {provenance.engine_executable_sha256}</p>}
      {provenance.runtime_identity_sha256 === null ? null : <p className="mt-1 break-all font-mono text-xs">runtime identity: {provenance.runtime_identity_sha256}</p>}
      {provenance.dependency_lock_sha256 === null ? null : <p className="mt-1 break-all font-mono text-xs">dependency lock: {provenance.dependency_lock_sha256}</p>}
      <p className="mt-1 font-mono text-xs">
        determinism canary: {deterministic.two_start_canary_passed ? "passed" : "not recorded"} · engine evidence: {deterministic.engine_log_semantic_verdict ? "verified" : "not verified"}
      </p>
      <p className="mt-1 font-mono text-xs">
        model dtype: {numerics.dtype ?? "n/a"} · KV cache: {numerics.kv_cache_quant ?? "n/a"} · SSM cache: {numerics.mamba_ssm_cache_dtype ?? "n/a"} · declared SSM: {numerics.model_config_mamba_ssm_dtype ?? "n/a"}
      </p>
      {snapshot === null ? null : (
        <div className="mt-2 border-t border-bench-line/70 pt-2 font-mono text-xs">
          <p>snapshot: {snapshot.repo}@{snapshot.revision}</p>
          <p className="break-all">merkle sha256: {snapshot.merkle_sha256}</p>
          <p>{snapshot.files.length} hashed snapshot file{snapshot.files.length === 1 ? "" : "s"}</p>
          <details className="mt-1">
            <summary className="cursor-pointer text-bench-accent">per-file hashes</summary>
            <ul className="mt-1 space-y-1">
              {snapshot.files.map((file) => <li key={file.path} className="break-all">{file.path}: {file.sha256}</li>)}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}
