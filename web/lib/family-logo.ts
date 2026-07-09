// Organization marks shown next to model names as scanning aids (the artificialanalysis.ai
// pattern). Assets are the orgs' own Hugging Face avatars, bundled under public/logos/.
// Matching runs on the MODEL LABEL, not the weights family: family encodes lineage, so a
// community fine-tune like Qwopus carries family "Qwen3.6" — keying on the label means only
// models that carry the org's own name ("Qwen3.6 27B", "Gemma 4 12B") get the mark, and
// fine-tunes with their own names keep the color-dot fallback instead of a misattributed logo.
// Names/logos identify the model's maker; listing is evaluation, not endorsement (see footer).

export type OrgLogo = {
  readonly src: string;
  readonly orgLabel: string;
};

const RULES: readonly { readonly pattern: RegExp; readonly logo: OrgLogo }[] = [
  { pattern: /^(qwen|qwq)/i, logo: { src: "/logos/qwen.jpg", orgLabel: "Qwen (Alibaba)" } },
  { pattern: /^gemma/i, logo: { src: "/logos/google.png", orgLabel: "Google" } },
  { pattern: /^deepseek/i, logo: { src: "/logos/deepseek.png", orgLabel: "DeepSeek" } },
  { pattern: /^llama/i, logo: { src: "/logos/meta.png", orgLabel: "Meta" } },
  { pattern: /^(mistral|ministral|mixtral)/i, logo: { src: "/logos/mistral.png", orgLabel: "Mistral AI" } },
  { pattern: /^phi/i, logo: { src: "/logos/microsoft.png", orgLabel: "Microsoft" } },
  { pattern: /^yi/i, logo: { src: "/logos/01ai.png", orgLabel: "01.AI" } },
  { pattern: /^glm/i, logo: { src: "/logos/zhipu.png", orgLabel: "Z.ai (GLM)" } },
  { pattern: /^command/i, logo: { src: "/logos/cohere.png", orgLabel: "Cohere" } },
  { pattern: /^gpt[ -]oss/i, logo: { src: "/logos/openai.png", orgLabel: "OpenAI" } },
];

export function orgLogoForModelLabel(modelLabel: string | null | undefined): OrgLogo | null {
  if (modelLabel === null || modelLabel === undefined) {
    return null;
  }
  return RULES.find((rule) => rule.pattern.test(modelLabel))?.logo ?? null;
}
