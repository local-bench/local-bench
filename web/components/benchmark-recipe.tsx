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
      {recipe.serveCommand ? (
        <CommandBlock title="Step 1 · start the model (leave running)" command={recipe.serveCommand} />
      ) : (
        <div className="rounded border border-bench-line bg-bench-panel-2/70 px-3 py-3 text-sm leading-6 text-bench-muted">
          <span className="font-mono text-[11px] uppercase text-bench-muted">Step 1 · start the model</span>
          <p className="mt-1">{recipe.serveNote}</p>
        </div>
      )}
      {recipe.serveCommand && recipe.serveNote ? (
        <p className="font-mono text-[11px] text-bench-muted">{recipe.serveNote}</p>
      ) : null}
      <CommandBlock title="Step 2 · benchmark it (second terminal)" command={recipe.benchCommand} />
      {recipe.lane === "capped-thinking" && !recipe.activationConfident ? (
        <p className="rounded border border-bench-warn/35 bg-bench-warn/10 p-2 font-mono text-[11px] text-bench-warn">
          Reasoning activation defaulted to qwen3 · confirm the right --reasoning-activation for this model family before
          you rely on the result.
        </p>
      ) : null}
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Do not change sampling, context, or prompt-template settings unless the recipe says so. VRAM tiers are
        recommendations, not guaranteed fits · close other GPU workloads.
      </p>
    </div>
  );
}
