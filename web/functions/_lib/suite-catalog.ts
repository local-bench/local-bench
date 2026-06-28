export type SuiteFile = {
  readonly path: string;
  readonly sha256: string;
  readonly size: number;
};

export type SuiteRecord = {
  readonly files: readonly SuiteFile[];
  readonly id: string;
  readonly suiteHash: string;
  readonly version: string;
};

export const CORE_TEXT_SUITE: SuiteRecord = {
  files: [
    {
      path: "suite.json",
      sha256: "d386f9438793625e20f111aabc51029aa08e7eec87b6798f7b68361f6dfa0d37",
      size: 3321,
    },
    {
      path: "itemsets.lock.json",
      sha256: "2bd295c093835845d1a1b99f4bad5bd0d3a11dc3cb6e90596253bbe8b1a98934",
      size: 1072,
    },
    {
      path: "mmlu_pro.jsonl",
      sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4",
      size: 287076,
    },
    {
      path: "ifbench.jsonl",
      sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257",
      size: 141566,
    },
    {
      path: "tc_json_v1.jsonl",
      sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74",
      size: 497028,
    },
    {
      path: "SCORECARD.json",
      sha256: "d26d7089cdc5ff5b31e6d89ca52516b9c250d6ad50f8d99d21ccb77c99f55459",
      size: 5565,
    },
    {
      path: "ATTRIBUTION.md",
      sha256: "1d34d25b8b3e70dacc244567a756c262e20bcc4aad436d93c495a9b18c841c45",
      size: 633,
    },
    {
      path: "CHANGES.md",
      sha256: "d129d7fff9925df20aded7c219cacbe9b1313f62b58e7c94d5f637ae96d75057",
      size: 490,
    },
    {
      path: "NOTICE",
      sha256: "5e8e0b3f70fa0ededfb282b375dc4c47b5f6dbedb90567d5d6069692c1a0c776",
      size: 692,
    },
    {
      path: "SHA256SUMS",
      sha256: "628035448027b2f38cb033e0144299236529519a46be2450072f8b7ada38e8b6",
      size: 1170,
    },
    {
      path: "SOURCE_REVISIONS.md",
      sha256: "896a83cc9cbc746a2544b232babb2f0f3e905454010ded1bed8bc0d5efb3fe85",
      size: 643,
    },
  ],
  id: "core-text-v1",
  suiteHash: "6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179",
  version: "core-text-v1",
} as const;

export function suiteById(id: string): SuiteRecord | null {
  return id === CORE_TEXT_SUITE.id ? CORE_TEXT_SUITE : null;
}
