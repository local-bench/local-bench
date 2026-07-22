// Submitters declare model names in whatever form their tooling emits — often a slugified
// twin of the catalog name ("bonsai-27b-ternary" vs "Bonsai 27B Ternary"). A "declared as"
// annotation only carries information when the declared identity genuinely differs, so
// comparisons ignore case, separators, and punctuation.
export function sameModelName(left: string, right: string): boolean {
  return normalizeModelName(left) === normalizeModelName(right);
}

function normalizeModelName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/gu, "");
}

// Compact label for a variant shown in the context of another model's page or chart: drop
// the tokens the variant name shares with the context name ("Qwopus 3.6 27B v2 MTP" in the
// "Qwen3.6 27B" context → "Qwopus v2 MTP"), keeping declaration order. A token is dropped
// when it matches a context token exactly or is a fragment of one ("3.6" inside "qwen3.6").
// Falls back to the full name when everything would be dropped.
export function variantNameInContext(name: string, contextName: string): string {
  const contextTokens = contextName.toLowerCase().split(/[\s/_-]+/u).filter(Boolean);
  const kept = name.split(/[\s/_-]+/u).filter(Boolean).filter((token) => {
    const lower = token.toLowerCase();
    return !contextTokens.some(
      (context) => context === lower || (lower.length >= 2 && context.includes(lower)),
    );
  });
  return kept.length === 0 ? name : kept.join(" ");
}
