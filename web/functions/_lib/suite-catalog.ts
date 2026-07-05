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
      sha256: "c084b2595554f651a4a79f80b640ed2f374de0ee4aa0b2360fda74b9f31ec3c2",
      size: 1960,
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
      sha256: "46b6462ba8c3b1326201f05de674dee1de3ab0a0aac933a0fc3a21836427f422",
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
      sha256: "c084b2595554f651a4a79f80b640ed2f374de0ee4aa0b2360fda74b9f31ec3c2",
      size: 1960,
    },
    {
      path: "SHA256SUMS",
      sha256: "afeab2effb1faf3b30e46863c622973e90f6047076d98331ba2d58628ab0e308",
      size: 1259,
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
      sha256: "07040cdc512fd5825311f250ba894d55e7bc7ca7c98a0d6f67e0e4cb477b4486",
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
  suiteManifestSha256: "487f337ac436c8b3ee327394cd9efc6d0f5562cbe1966ce114ebb611f18c8a53",
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
    { path: "SCORECARD.json", sha256: "c084b2595554f651a4a79f80b640ed2f374de0ee4aa0b2360fda74b9f31ec3c2", size: 1960 },
    { path: "SHA256SUMS", sha256: "5b179f9254b903ac2aa40b38862b21b917656c0048ab9aafca124cb12f0530c7", size: 1259 },
    { path: "SOURCE_REVISIONS.md", sha256: "486315998e11e0353eea0b2338bd90440f9895832272673bcd81a486205bc66c", size: 396 },
    { path: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257", size: 141566 },
    { path: "itemsets.lock.json", sha256: "6a19a23e74e906759444b559d4378a839319cce9cef0484c562b5131651a2218", size: 1488 },
    { path: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf", size: 179626 },
    { path: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4", size: 287076 },
    { path: "suite.json", sha256: "bbcacd68b8181f95d18f8fefef488ccb406b3f2becf7d769a8c77bd4c6b732b2", size: 3188 },
    { path: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74", size: 497028 },
    { path: "suite_release_manifest.json", sha256: "3bd0981c675875a607e19e13c6f5b5c081c4ff181d0c6d2edde3439234b21dbc", size: 3909 },
  ],
  id: "suite-v1-text-code-agentic-5axis-v1",
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"],
  suiteHash: "de25c8064f2342ef1f59a6a99065f7fe8dd17b389a899f0db3ce197f64f3fbf3",
  suiteManifestSha256: "db1e6cd14f946126254cc2ada56ea1af0186303e0899f00f374d30382d96870e",
  version: "suite-v1",
} as const;

export const PUBLIC_SUITES = [CORE_TEXT_SUITE, FOUR_AXIS_SUITE, FIVE_AXIS_SUITE] as const;

export function suiteById(id: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === id) ?? null;
}

export function suiteByReleasePair(releaseId: string, manifestSha256: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === releaseId && suite.suiteManifestSha256 === manifestSha256) ?? null;
}
