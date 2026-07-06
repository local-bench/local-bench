import Link from "next/link";
import { CopyButton } from "@/components/copy-button";
import type { BenchmarkRecipe as Recipe } from "@/lib/onramp";

const IDENTITY_COPY: Record<Recipe["identityMode"], string> = {
  full: "Identity: full - HF tokenizer/template cached; tokenizer and chat-template digests recorded.",
  basic:
    "Identity: basic - server-side template introspection; tokenizer/chat-template digests will be null. Add the model's exact non-GGUF HF repo for strongest provenance.",
};

export function copyableCommand(command: string): string {
  return command.replace(/[ \t]*\\\r?\n[ \t]*/g, " ").trim();
}

function CommandBlock({ title, command }: { readonly title: string; readonly command: string }) {
  const copiedCommand = copyableCommand(command);
  const copiesSingleLine = copiedCommand !== command;
  return (
    <div className="rounded border border-bench-line bg-bench-panel-2/70">
      <div className="flex items-center justify-between gap-3 border-b border-bench-line px-3 py-2">
        <span className="font-mono text-[11px] uppercase text-bench-muted">{title}</span>
        <div className="flex items-center gap-2">
          {copiesSingleLine ? <span className="font-mono text-[10px] text-bench-muted">copies as one line</span> : null}
          <CopyButton value={copiedCommand} />
        </div>
      </div>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-xs leading-6 text-bench-text">{command}</pre>
    </div>
  );
}

export function BenchmarkRecipe({ recipe }: { readonly recipe: Recipe }) {
  return (
    <div className="mt-5 flex flex-col gap-3" data-testid="benchmark-recipe">
      <p className="font-mono text-xs text-bench-muted">
        localbench does not download or run the model. First start a local server, then localbench sends the benchmark to
        that endpoint.
      </p>
      <p className="font-mono text-xs text-bench-muted">
        Strongest provenance: let the CLI launch the pinned server itself with{" "}
        <span className="font-mono text-bench-text">localbench bench</span> — see{" "}
        <Link href="/submit" className="text-bench-accent hover:underline">
          how to submit
        </Link>
        .
      </p>
      <p className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase text-bench-accent">
        <span>Board-ranked · {recipe.lane} · profile auto · suite-v1-full-exec-6axis-v1</span>
        {recipe.ggufRepo !== null ? (
          <a
            href={`https://huggingface.co/${recipe.ggufRepo}`}
            target="_blank"
            rel="noreferrer"
            className="text-bench-muted hover:text-bench-accent"
            aria-label={`${recipe.ggufRepo} GGUF repo on Hugging Face`}
          >
            HF ↗
          </a>
        ) : null}
      </p>
      <p
        className={[
          "rounded border px-3 py-2 font-mono text-[11px] leading-5",
          recipe.identityMode === "full"
            ? "border-bench-accent/40 bg-bench-accent/10 text-bench-accent"
            : "border-bench-warn/50 bg-bench-warn/10 text-bench-warn",
        ].join(" ")}
      >
        {IDENTITY_COPY[recipe.identityMode]}
      </p>
      {recipe.model.baseModelDisplayName !== null ? (
        <p className="font-mono text-[11px] text-bench-muted">
          Fine-tune of <span className="text-bench-text">{recipe.model.baseModelDisplayName}</span>
        </p>
      ) : null}
      <CommandBlock title="Step 1 · one-time setup" command={recipe.setupCommand} />
      <p className="font-mono text-[11px] text-bench-muted">
        Python 3.11+. fetch-suite verifies the sha256-pinned item sets and caches them locally.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Gated repo (e.g. google/gemma-*)? Run <span className="font-mono text-bench-text">hf auth login</span> after
        accepting the license on huggingface.co. llama-server reads its token from the{" "}
        <span className="font-mono text-bench-text">HF_TOKEN</span> env var for gated GGUF downloads.
      </p>
      {recipe.serveCommand ? (
        <CommandBlock title="Step 2 · start the model (leave running)" command={recipe.serveCommand} />
      ) : (
        <div className="rounded border border-bench-line bg-bench-panel-2/70 px-3 py-3 text-sm leading-6 text-bench-muted">
          <span className="font-mono text-[11px] uppercase text-bench-muted">Step 2 · start the model</span>
          <p className="mt-1">{recipe.serveNote}</p>
        </div>
      )}
      {recipe.serveCommand && recipe.serveNote ? (
        <p className="font-mono text-[11px] text-bench-muted">{recipe.serveNote}</p>
      ) : null}
      <p className="font-mono text-[11px] leading-5 text-bench-warn">
        This is a full ranked run — many hours of GPU time. Preflight fails fast (seconds) if the server, model, template,
        or context is not acceptable.
      </p>
      <CommandBlock title="Step 3 · benchmark it (second terminal)" command={recipe.benchCommand} />
      <CommandBlock title="Step 4 · submit to the board" command={recipe.submitCommand} />
      <p className="font-mono text-[11px] text-bench-muted">
        Prints your submission id. Nothing publishes until maintainer review.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Do not change sampling, context, or prompt-template settings unless the recipe says so. VRAM values are
        8k-context estimates; the ranked recipe pins 32k context — you may need one quant tier smaller. Close other GPU
        workloads.
      </p>
    </div>
  );
}
