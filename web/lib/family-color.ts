export type FamilyStyle = { readonly label: string; readonly color: string };

// Brand-ish hues, tuned for legibility on the dark bench background. Matched by substring so
// "qwen3.5-9b", "c4ai-command-r-plus", etc. resolve to their company. Unmatched families get a
// stable colour from FALLBACK (hashed) so every family is at least consistently distinguishable.
const BRANDS: ReadonlyArray<{ readonly match: readonly string[]; readonly label: string; readonly color: string }> = [
  { match: ["qwen", "qwq"], label: "Qwen", color: "#a78bfa" },
  { match: ["llama", "meta"], label: "Llama", color: "#4d8bff" },
  { match: ["gemma", "gemini"], label: "Gemma", color: "#4ade80" },
  { match: ["mistral", "mixtral", "ministral", "magistral", "devstral", "codestral"], label: "Mistral", color: "#ff8a3d" },
  { match: ["phi"], label: "Phi", color: "#38bdf8" },
  { match: ["deepseek"], label: "DeepSeek", color: "#818cf8" },
  { match: ["command", "cohere", "aya"], label: "Cohere", color: "#ff7aa8" },
  { match: ["yi"], label: "Yi", color: "#f472b6" },
  { match: ["granite"], label: "Granite", color: "#22d3ee" },
  { match: ["olmo"], label: "OLMo", color: "#facc15" },
  { match: ["nemotron", "nvidia"], label: "Nemotron", color: "#9ccc1f" },
];

const FALLBACK = ["#94a3b8", "#f59e0b", "#34d399", "#fb7185", "#60a5fa", "#c084fc", "#a3e635", "#e879f9"] as const;

export function familyStyle(family: string): FamilyStyle {
  const key = family.toLowerCase();
  for (const brand of BRANDS) {
    if (brand.match.some((needle) => key.includes(needle))) {
      return { label: brand.label, color: brand.color };
    }
  }
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) >>> 0;
  }
  return { label: family, color: FALLBACK[hash % FALLBACK.length] ?? "#94a3b8" };
}
