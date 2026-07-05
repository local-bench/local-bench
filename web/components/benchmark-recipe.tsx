import Link from "next/link";
import { CopyButton } from "@/components/copy-button";
import type { BenchmarkRecipe as Recipe } from "@/lib/onramp";

function CommandBlock({ title, command }: { readonly title: string; readonly command: string }) {
  return (
    <div className="rounded border border-bench-line bg-bench-panel-2/70">
      <div className="flex items-center justify-between gap-3 border-b border-bench-line px-3 py-2">
        <span className="font-mono text-[11px] uppercase text-bench-muted">{title}</span>
        <CopyButton value={command} />
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
      {recipe.model.baseModelDisplayName !== null ? (
        <p className="font-mono text-[11px] text-bench-muted">
          Fine-tune of <span className="text-bench-text">{recipe.model.baseModelDisplayName}</span>
        </p>
      ) : null}
      <CommandBlock title="Step 1 · one-time setup" command={recipe.setupCommand} />
      <p className="font-mono text-[11px] text-bench-muted">
        Python 3.11+. fetch-suite verifies the sha256-pinned item sets and caches them locally.
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
      <CommandBlock title="Step 3 · benchmark it (second terminal)" command={recipe.benchCommand} />
      <CommandBlock title="Step 4 · submit to the board" command={recipe.submitCommand} />
      <p className="font-mono text-[11px] text-bench-muted">
        Prints your submission id. Nothing publishes until maintainer review.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Do not change sampling, context, or prompt-template settings unless the recipe says so. VRAM tiers are
        recommendations, not guaranteed fits · close other GPU workloads.
      </p>
    </div>
  );
}
