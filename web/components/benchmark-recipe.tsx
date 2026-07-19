import Link from "next/link";
import { CopyButton } from "@/components/copy-button";
import type { BenchmarkRecipe as Recipe } from "@/lib/onramp";

const IDENTITY_COPY: Record<Recipe["identityMode"], string> = {
  full: "Identity: full - HF tokenizer/template cached; tokenizer and chat-template digests recorded.",
  basic:
    "Identity: basic - server-side template introspection; tokenizer/chat-template digests will be null. Add the model's exact non-GGUF HF repo for strongest provenance.",
};

const LINEAGE_KIND_COPY: Record<Recipe["model"]["modelKind"], string> = {
  base: "variant",
  finetune: "fine-tune",
  distill: "distill",
  merge: "merge",
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

function isOfficialVariant(model: Recipe["model"]): boolean {
  const baseOrg = model.baseModelId?.split("/")[0]?.toLowerCase() ?? null;
  return baseOrg !== null && model.org.toLowerCase() === baseOrg;
}

function lineageLine(model: Recipe["model"]): string {
  // Gate on baseModelSlug: base_model pointing OUTSIDE the catalog (a lab's own "-Base"
  // pretrain) does not make this a variant — the picker lists it as an original release.
  if (model.baseModelSlug === null || model.baseModelDisplayName === null) {
    return `Benchmarking ${model.displayName} — Original release`;
  }
  const kind = isOfficialVariant(model) ? "official variant" : LINEAGE_KIND_COPY[model.modelKind];
  return `Benchmarking ${model.displayName} — ${kind} of ${model.baseModelDisplayName} · by ${model.org}`;
}

function PipNamespaceWarning() {
  return (
    <p className="font-mono text-[11px] leading-5 text-bench-warn">
      The package name is <span className="text-bench-text">local-bench-ai</span>. Plain{" "}
      <span className="text-bench-text">pip install localbench</span> installs an unrelated third-party
      package — use the exact command above.
    </p>
  );
}

function RequirementsLine() {
  return (
    <p className="font-mono text-[11px] leading-5 text-bench-muted">
      Tested on Windows 11; any OS that runs Python 3.11+ and llama-server on PATH works for the
      public static path, while the full six-axis lane also needs Windows with WSL2. Install
      llama.cpp from{" "}
      <a
        href="https://github.com/ggerganov/llama.cpp/releases"
        target="_blank"
        rel="noreferrer"
        className="text-bench-accent underline"
      >
        github.com/ggerganov/llama.cpp/releases
      </a>{" "}
      or pass <span className="font-mono text-bench-text">--llama-server-path</span>.
    </p>
  );
}

function RecipeMetadata({ recipe }: { readonly recipe: Recipe }) {
  return (
    <>
      <p className="font-mono text-xs text-bench-accent">{lineageLine(recipe.model)}</p>
      <p className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase text-bench-accent">
        <span>
          {recipe.lead.kind === "unavailable"
            ? `Managed full path · ${recipe.lane} · suite-v1-full-exec-6axis-v1`
            : "Public path · measured/static · suite-v1-static-exec-5axis-v1"}
        </span>
        {recipe.runtimeId !== "vllm" && recipe.ggufRepo !== null ? (
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
    </>
  );
}

function OneCommandLead({
  recipe,
  lead,
}: {
  readonly recipe: Recipe;
  readonly lead: Extract<Recipe["lead"], { readonly command: string }>;
}) {
  const localOnly = lead.kind === "local-only";
  return (
    <div className="flex flex-col gap-3">
      <p className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase text-bench-accent">
        <span className="rounded border border-bench-accent/40 px-2 py-1">{localOnly ? "LOCAL-ONLY" : "Recommended"}</span>
        <span>{localOnly ? "raw Hugging Face repo run" : "catalog-pinned one-command flow"}</span>
      </p>
      <CommandBlock title="Step 1 · install" command={recipe.installCommand} />
      <PipNamespaceWarning />
      <CommandBlock title="Step 2 · bench, score, and optional submit" command={lead.command} />
      <RequirementsLine />
      {localOnly ? (
        <p className="font-mono text-[11px] leading-5 text-bench-warn">
          Raw Hugging Face repos run local-only in localbench 0.3.2. The managed path below is publishable when you
          can provide the model file and identity metadata.
        </p>
      ) : (
        <p className="font-mono text-[11px] leading-5 text-bench-muted">
          The command verifies downloads against pinned hashes, checks publishability before starting, and asks before
          submitting.
        </p>
      )}
      <p className="font-mono text-[11px] leading-5 text-bench-warn">
        Public path: <span className="font-mono text-bench-text">--static-only</span> runs the five non-agentic axes and
        is not eligible for the full six-axis index. Full execution fails fast before model download unless both
        <span className="font-mono text-bench-text"> --wsl-venv-python</span> and
        <span className="font-mono text-bench-text"> --appworld-root</span> configure the managed AppWorld harness.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Non-TTY runs must pass explicit <span className="font-mono text-bench-text">--yes</span>,{" "}
        <span className="font-mono text-bench-text">--accept-suite-terms</span>, and either{" "}
        <span className="font-mono text-bench-text">--no-submit</span> or{" "}
        <span className="font-mono text-bench-text">--submit</span>.
      </p>
    </div>
  );
}

function ClassicRecipeBody({ recipe }: { readonly recipe: Recipe }) {
  return (
    <div className="flex flex-col gap-3">
      <CommandBlock title="Step 1 · one-time setup" command={recipe.setupCommand} />
      <PipNamespaceWarning />
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
        Prints your submission id. Complete runs publish immediately, then are subject to post-hoc moderation.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Do not change sampling, context, or prompt-template settings unless the recipe says so. VRAM values are
        8k-context estimates; the ranked recipe pins 32k context — you may need one quant tier smaller. Close other GPU
        workloads.
      </p>
    </div>
  );
}

function AdvancedClassicRecipe({ recipe }: { readonly recipe: Recipe }) {
  return (
    <details className="rounded border border-bench-line bg-bench-panel-2/40 p-3">
      <summary className="cursor-pointer font-mono text-xs font-semibold text-bench-accent">
        Advanced: bring your own server (vLLM, custom rigs)
      </summary>
      <div className="mt-3">
        <p className="mb-3 font-mono text-[11px] leading-5 text-bench-muted">
          Use the classic path when you run your own OpenAI-compatible server or need explicit publishable metadata.
        </p>
        <ClassicRecipeBody recipe={recipe} />
      </div>
    </details>
  );
}

function MaintainerVllmRecipe({ recipe }: { readonly recipe: Recipe }) {
  if (recipe.lead.kind !== "maintainer") return null;
  return (
    <div className="flex flex-col gap-3 rounded border border-bench-warn/50 bg-bench-warn/10 p-3">
      <p className="font-mono text-[11px] font-semibold uppercase text-bench-warn">vLLM maintainer lane</p>
      <CommandBlock title="Pinned safetensors / NVFP4 run" command={recipe.lead.command} />
      <p className="font-mono text-[11px] leading-5 text-bench-warn-soft">
        This is a maintainer-operated WSL2 lane for immutable safetensors snapshots. It requires the pinned vLLM environment,
        managed AppWorld paths, and the two-start determinism canary. The community path remains llama.cpp/GGUF until the
        appliance ships.
      </p>
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Replace every &lt;placeholder&gt; with the corresponding pinned WSL distro, vLLM environment, and managed AppWorld path.
      </p>
    </div>
  );
}

export function BenchmarkRecipe({ recipe }: { readonly recipe: Recipe }) {
  return (
    <div className="mt-5 flex flex-col gap-3" data-testid="benchmark-recipe">
      <RecipeMetadata recipe={recipe} />
      {recipe.lead.kind === "maintainer" ? (
        <MaintainerVllmRecipe recipe={recipe} />
      ) : recipe.lead.kind === "unavailable" ? (
        <>
          <p className="rounded border border-bench-warn/50 bg-bench-warn/10 px-3 py-2 font-mono text-[11px] leading-5 text-bench-warn">
            {recipe.lead.reason}
          </p>
          <ClassicRecipeBody recipe={recipe} />
        </>
      ) : (
        <>
          <OneCommandLead recipe={recipe} lead={recipe.lead} />
          <AdvancedClassicRecipe recipe={recipe} />
        </>
      )}
      <p className="font-mono text-xs text-bench-muted">
        See{" "}
        <Link href="/submit" className="text-bench-accent underline">
          how to submit
        </Link>{" "}
        for the full loop and trust labels.
      </p>
    </div>
  );
}
