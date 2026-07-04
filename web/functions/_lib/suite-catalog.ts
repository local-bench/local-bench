export type SuiteFile = {
  readonly path: string;
  readonly sha256: string;
  readonly size: number;
};

export type SuiteRecord = {
  readonly files: readonly SuiteFile[];
  readonly id: string;
  readonly staticBenches: readonly string[];
  readonly suiteHash: string;
  readonly suiteManifestSha256: string;
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
      path: "LICENSES/BFCL-Apache-2.0",
      sha256: "801f2893851e1d05c434e6985fe3e7b5a0ab4e194b71f9b37649029f3d910ee0",
      size: 9073,
    },
    {
      path: "LICENSES/IFBench-ODC-BY-1.0",
      sha256: "275ebb27595e33a98af9798a7de56003ae78529f3695790a047ee301b27437a9",
      size: 20276,
    },
    {
      path: "LICENSES/IFEval-Apache-2.0",
      sha256: "09ee2bff51da5a25e5ab5c757f73a832ce1b016deb3971291ec2cca9128c4c3f",
      size: 9230,
    },
    {
      path: "LICENSES/MMLU-Pro-MIT",
      sha256: "9eb6f69d48a1dd764e8a33f14a584f460d3cec653477c136a95dd6df9c249211",
      size: 1055,
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
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1"],
  suiteHash: "6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179",
  suiteManifestSha256: "6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179",
  version: "core-text-v1",
} as const;

export const FOUR_AXIS_SUITE: SuiteRecord = {
  files: [
    {
      path: "ATTRIBUTION.md",
      sha256: "57ca152e665b8b0ed70b97b3ece26fc96132fb439a649a21bc6516410c40ff76",
      size: 334,
    },
    {
      path: "CHANGES.md",
      sha256: "5af40f8d3f8a7ad1b9b18881db8d7e30d91bf77063f1f110a8df75dfd0c97c8d",
      size: 250,
    },
    {
      path: "LICENSES/BFCL-Apache-2.0",
      sha256: "801f2893851e1d05c434e6985fe3e7b5a0ab4e194b71f9b37649029f3d910ee0",
      size: 9073,
    },
    {
      path: "LICENSES/IFBench-ODC-BY-1.0",
      sha256: "275ebb27595e33a98af9798a7de56003ae78529f3695790a047ee301b27437a9",
      size: 20276,
    },
    {
      path: "LICENSES/LiveCodeBench-CC-BY-4.0-NOTICE",
      sha256: "8ef9493c6c2b59caf6723d93518c7bca6ce2d5b254fa478b2a2afcadd4f39c0f",
      size: 237,
    },
    {
      path: "LICENSES/MMLU-Pro-MIT",
      sha256: "9eb6f69d48a1dd764e8a33f14a584f460d3cec653477c136a95dd6df9c249211",
      size: 1055,
    },
    {
      path: "NOTICE",
      sha256: "cf74fb413bdedd58b212ad642856b6842d1e986e6a20c0ddb220c4af8cffc4f2",
      size: 717,
    },
    {
      path: "SCORECARD.json",
      sha256: "556a9f9bb1127803cdc71e8b8d0ae4247fb075ab7005a0d05608424dfab4c420",
      size: 3818,
    },
    {
      path: "SHA256SUMS",
      sha256: "bb35e6eae5753995e078446eee25eae98e88ca7a856ac2248a1e4148ffd8a54d",
      size: 1274,
    },
    {
      path: "SOURCE_REVISIONS.md",
      sha256: "486315998e11e0353eea0b2338bd90440f9895832272673bcd81a486205bc66c",
      size: 396,
    },
    {
      path: "ifbench.jsonl",
      sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257",
      size: 141566,
    },
    {
      path: "itemsets.lock.json",
      sha256: "6a19a23e74e906759444b559d4378a839319cce9cef0484c562b5131651a2218",
      size: 1488,
    },
    {
      path: "lcb.jsonl",
      sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf",
      size: 179626,
    },
    {
      path: "mmlu_pro.jsonl",
      sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4",
      size: 287076,
    },
    {
      path: "suite.json",
      sha256: "30ff63b82621c12b034a79013df7629d0e36b620fede2f63c4d1b10f70b6638a",
      size: 3196,
    },
    {
      path: "suite_release_manifest.json",
      sha256: "f4f01f47841a4b7ad8c4f0943105dcf064a9388e0793664702ee21e8ff9c52f7",
      size: 3896,
    },
    {
      path: "tc_json_v1.jsonl",
      sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74",
      size: 497028,
    },
  ],
  id: "suite-v1-partial-text-code-4axis-v1",
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"],
  suiteHash: "bf463bf8526baad676f0a87d743f0037fdc8eb50dc4faf6abc374b29833dd558",
  suiteManifestSha256: "b3fc40191c366d87b5537b12daa3d5c3680035238492c47996ab1f1b00d32231",
  version: "suite-v1",
} as const;

export const FIVE_AXIS_SUITE: SuiteRecord = {
  files: [
    { path: "ATTRIBUTION.md", sha256: "57ca152e665b8b0ed70b97b3ece26fc96132fb439a649a21bc6516410c40ff76", size: 334 },
    { path: "CHANGES.md", sha256: "f000f8c936c286091147cb1214446ac196521e301566142bea26f011d18df742", size: 252 },
    { path: "LICENSES/BFCL-Apache-2.0", sha256: "801f2893851e1d05c434e6985fe3e7b5a0ab4e194b71f9b37649029f3d910ee0", size: 9073 },
    { path: "LICENSES/IFBench-ODC-BY-1.0", sha256: "275ebb27595e33a98af9798a7de56003ae78529f3695790a047ee301b27437a9", size: 20276 },
    { path: "LICENSES/LiveCodeBench-CC-BY-4.0-NOTICE", sha256: "8ef9493c6c2b59caf6723d93518c7bca6ce2d5b254fa478b2a2afcadd4f39c0f", size: 237 },
    { path: "LICENSES/MMLU-Pro-MIT", sha256: "9eb6f69d48a1dd764e8a33f14a584f460d3cec653477c136a95dd6df9c249211", size: 1055 },
    { path: "NOTICE", sha256: "8e2e4264cf681282dafe1d0caf0b58b168f88b3acf6af0ee4fb7aad1a8776a92", size: 554 },
    { path: "SCORECARD.json", sha256: "556a9f9bb1127803cdc71e8b8d0ae4247fb075ab7005a0d05608424dfab4c420", size: 3818 },
    { path: "SHA256SUMS", sha256: "c6099eb5ad6a850431a9a4f80cd34cfb0b3fea6c5fa4715ba090756465258120", size: 1259 },
    { path: "SOURCE_REVISIONS.md", sha256: "486315998e11e0353eea0b2338bd90440f9895832272673bcd81a486205bc66c", size: 396 },
    { path: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257", size: 141566 },
    { path: "itemsets.lock.json", sha256: "6a19a23e74e906759444b559d4378a839319cce9cef0484c562b5131651a2218", size: 1488 },
    { path: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf", size: 179626 },
    { path: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4", size: 287076 },
    { path: "suite.json", sha256: "bbcacd68b8181f95d18f8fefef488ccb406b3f2becf7d769a8c77bd4c6b732b2", size: 3188 },
    { path: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74", size: 497028 },
    { path: "suite_release_manifest.json", sha256: "86e56a61fc75114ffd264cd0538c4c939567a79b5008b86d0cb310492905f625", size: 3909 },
  ],
  id: "suite-v1-text-code-agentic-5axis-v1",
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"],
  suiteHash: "de25c8064f2342ef1f59a6a99065f7fe8dd17b389a899f0db3ce197f64f3fbf3",
  suiteManifestSha256: "5a47282a55621cbb9be4b719c1f9bba2f740d7720ef594fa00e794355cc420f9",
  version: "suite-v1",
} as const;

export const PUBLIC_SUITES = [CORE_TEXT_SUITE, FOUR_AXIS_SUITE, FIVE_AXIS_SUITE] as const;

export function suiteById(id: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === id) ?? null;
}

export function suiteByReleasePair(releaseId: string, manifestSha256: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === releaseId && suite.suiteManifestSha256 === manifestSha256) ?? null;
}
