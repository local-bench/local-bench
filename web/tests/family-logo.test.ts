import { describe, expect, it } from "vitest";
import { orgLogoForModelLabel } from "../lib/family-logo";

describe("orgLogoForModelLabel", () => {
  it.each([
    ["Qwen3.6 27B", "Qwen (Alibaba)"],
    ["QwQ 32B", "Qwen (Alibaba)"],
    ["Gemma 4 12B", "Google"],
    ["DeepSeek R1 Distill Llama 8B", "DeepSeek"],
    ["Llama 3.1 8B", "Meta"],
    ["Mixtral 8x7B", "Mistral AI"],
    ["Ministral 8B", "Mistral AI"],
    ["Phi 4", "Microsoft"],
    ["Yi 1.5 9B", "01.AI"],
    ["GLM 5 Air", "Z.ai (GLM)"],
    ["Command R 35B", "Cohere"],
    ["GPT OSS 20B", "OpenAI"],
  ])("maps %s to the %s mark", (label, org) => {
    expect(orgLogoForModelLabel(label)?.orgLabel).toBe(org);
  });

  it("never stamps an org mark on fine-tunes with their own names", () => {
    // Qwopus is a community fine-tune whose weights FAMILY is Qwen3.6 — the label-based
    // rule must not attribute it to Alibaba.
    expect(orgLogoForModelLabel("Qwopus 2.6 27B")).toBeNull();
    expect(orgLogoForModelLabel("Dolphin 3.0 Llama-Tune")).toBeNull();
    expect(orgLogoForModelLabel(null)).toBeNull();
    expect(orgLogoForModelLabel(undefined)).toBeNull();
  });
});
