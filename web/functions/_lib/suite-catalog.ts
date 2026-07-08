export type SuiteFile = {
  readonly path: string;
  readonly sha256: string;
  readonly size: number;
};

export type SuiteRecord = {
  readonly files: readonly SuiteFile[];
  readonly id: string;
  readonly legacy?: boolean;
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
      sha256: "f16203bf5ce513d504f3d50ec15b4cf1176a8870bd388829fe46d2aca4e1c4ec",
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
      sha256: "dd69be60ff23189903ae31e4677d195e57505933c2adc0bb00087008ebd19392",
      size: 1170,
    },
    {
      path: "SOURCE_REVISIONS.md",
      sha256: "896a83cc9cbc746a2544b232babb2f0f3e905454010ded1bed8bc0d5efb3fe85",
      size: 643,
    },
  ],
  id: "core-text-v1",
  legacy: true,
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
      sha256: "f16203bf5ce513d504f3d50ec15b4cf1176a8870bd388829fe46d2aca4e1c4ec",
      size: 1960,
    },
    {
      path: "SHA256SUMS",
      sha256: "31637aa90305f15be40cfb2ff0d041bf28346458642d6079b8d710fdd82bf2b4",
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
      sha256: "135f902b782a8a4c1017aad9aa3e9076719664695aa36e38069302fd330c8482",
      size: 3896,
    },
    {
      path: "tc_json_v1.jsonl",
      sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74",
      size: 497028,
    },
  ],
  id: "suite-v1-partial-text-code-4axis-v1",
  legacy: true,
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"],
  suiteHash: "bf463bf8526baad676f0a87d743f0037fdc8eb50dc4faf6abc374b29833dd558",
  suiteManifestSha256: "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7",
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
    { path: "SCORECARD.json", sha256: "f16203bf5ce513d504f3d50ec15b4cf1176a8870bd388829fe46d2aca4e1c4ec", size: 1960 },
    { path: "SHA256SUMS", sha256: "7b519df4cedc10fe1fb5ae7fd932289dea6edac8c6f535825daeffa72ee2f5b3", size: 1259 },
    { path: "SOURCE_REVISIONS.md", sha256: "486315998e11e0353eea0b2338bd90440f9895832272673bcd81a486205bc66c", size: 396 },
    { path: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257", size: 141566 },
    { path: "itemsets.lock.json", sha256: "6a19a23e74e906759444b559d4378a839319cce9cef0484c562b5131651a2218", size: 1488 },
    { path: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf", size: 179626 },
    { path: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4", size: 287076 },
    { path: "suite.json", sha256: "bbcacd68b8181f95d18f8fefef488ccb406b3f2becf7d769a8c77bd4c6b732b2", size: 3188 },
    { path: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74", size: 497028 },
    { path: "suite_release_manifest.json", sha256: "b4ff32fb3d6ff87a162abe18af07d1a6b49ee24eb491e255cdb16861ecbd978f", size: 3909 },
  ],
  id: "suite-v1-text-code-agentic-5axis-v1",
  legacy: true,
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "lcb"],
  suiteHash: "de25c8064f2342ef1f59a6a99065f7fe8dd17b389a899f0db3ce197f64f3fbf3",
  suiteManifestSha256: "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f",
  version: "suite-v1",
} as const;

const EXEC_SUITE_FILES: readonly SuiteFile[] = [
  { path: "amo.jsonl", sha256: "98e79f1da84680345224f48fc7d1ed8b220e76cfd0525da1c494633d1abd1904", size: 24128 },
  { path: "bfcl.jsonl", sha256: "26d990d589db8a8b2a70b23c592ea0aff9df8287d9509a2fadd98d1b72661e17", size: 420003 },
  { path: "bfcl_multi_turn.jsonl", sha256: "c7f030d64098c4573c0c49b4d837f43b5f18047a941118bb77c8e2857e55f0f9", size: 2231316 },
  { path: "bigcodebench_hard.jsonl", sha256: "33635febb89ab6cb8f06e139bc33932ada89d90e32ce03820ad7f15712e19b8e", size: 849460 },
  { path: "ifbench.jsonl", sha256: "40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257", size: 141566 },
  { path: "itemsets.lock.json", sha256: "5ef89aa2949b8fc23da39f20c602e91fec3968d58c24b5fa3d84bb1815a8d3ff", size: 5215 },
  { path: "lcb.jsonl", sha256: "b9069940394e90cf7bd9a756d5b1907b38c088b56b8467ab5f97d2a9f160bdcf", size: 179626 },
  { path: "mmlu_pro.jsonl", sha256: "129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4", size: 287076 },
  { path: "olymmath_hard.jsonl", sha256: "8126598901f0e2be27b2a4fed97fded7b2c43aa37ca3ecb580527ad11a15e53b", size: 40716 },
  { path: "ruler_32k.jsonl", sha256: "0bede1810663a7164e68f3008248d78ba247fb677440f06b3e1c63b8781b0540", size: 50474 },
  { path: "suite.json", sha256: "809b5e2c9e8bbd24ac29b48698cfd141e2d1affa9ca847ac267ef1c6ac5de4b2", size: 5729 },
  { path: "supergpqa.jsonl", sha256: "1138cb40b4e7ab84da790e16fa44f9184220f35760e95802064a3522db1a537a", size: 264520 },
  { path: "tc_json_v1.jsonl", sha256: "571b3c4064b523174900883c786df4fdbb6c2a8924a148620a167415d67afd74", size: 497028 },
  { path: "templates/bfcl.txt", sha256: "db54c9aafd809974c5a1fc1663150354d34b1c76a8d8bef1d70dc7b5f4307589", size: 192 },
  { path: "templates/bfcl_multi_turn.txt", sha256: "3f349f401a42cdd3887664e8bd948a3a4701e31a5cc25f9e1848239fe7baea33", size: 98 },
  { path: "templates/bigcodebench.txt", sha256: "a697baa82796087b9ef55f485e21776e4e925a3ad68a4ed8a28a54ca5806bdfc", size: 256 },
  { path: "templates/ifbench.txt", sha256: "c3403df4243682bca4d3ed590c49c7548d3525a4e143505b7e5350959bdfe7f3", size: 9 },
  { path: "templates/lcb.txt", sha256: "6f48ef15224e006e1e900cc07f875bb35a8ba945d36d072bb4e2f1421ee453a1", size: 283 },
  { path: "templates/math.txt", sha256: "cda8025aee686b7732d21aa0d43e1684e299e155c1ece4a4b1a7923dd93ea4e0", size: 166 },
  { path: "templates/mcq_cot.txt", sha256: "f49427d8f4427b07d504ce70aa21097c7a35b470f09f10107b8e57133bf944fc", size: 106 },
  { path: "templates/ruler.txt", sha256: "12cca0402c7a9a10b27df71c049bc531f78d4b11d1e64fc6aac4c0bb9b636a62", size: 164 },
  { path: "templates/tc_json_v1.txt", sha256: "d98cbb51f82297886c92d6f39d206a94b981d50641b23306aeacc2b713843251", size: 663 },
] as const;

export const FULL_EXEC_SUITE: SuiteRecord = {
  files: EXEC_SUITE_FILES,
  id: "suite-v1-full-exec-6axis-v1",
  legacy: false,
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "bigcodebench_hard", "olymmath_hard", "amo"],
  suiteHash: "02874cffae45ddcb39688a5651b335a158c4096d148d20062908a382970254cc",
  suiteManifestSha256: "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
  version: "suite-v1",
} as const;

export const STATIC_EXEC_SUITE: SuiteRecord = {
  files: EXEC_SUITE_FILES,
  id: "suite-v1-static-exec-5axis-v1",
  legacy: false,
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "bigcodebench_hard", "olymmath_hard", "amo"],
  suiteHash: "02874cffae45ddcb39688a5651b335a158c4096d148d20062908a382970254cc",
  suiteManifestSha256: "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
  version: "suite-v1",
} as const;

export const STATIC_CORE_DIAG_SUITE: SuiteRecord = {
  files: EXEC_SUITE_FILES,
  id: "suite-v1-static-core-diag-v1",
  legacy: false,
  staticBenches: ["mmlu_pro", "ifbench", "tc_json_v1", "olymmath_hard", "amo"],
  suiteHash: "02874cffae45ddcb39688a5651b335a158c4096d148d20062908a382970254cc",
  suiteManifestSha256: "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69",
  version: "suite-v1",
} as const;

export const PUBLIC_SUITES = [
  FULL_EXEC_SUITE,
  STATIC_EXEC_SUITE,
  STATIC_CORE_DIAG_SUITE,
  CORE_TEXT_SUITE,
  FOUR_AXIS_SUITE,
  FIVE_AXIS_SUITE,
] as const;

export function suiteById(id: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === id) ?? null;
}

export function suiteByReleasePair(releaseId: string, manifestSha256: string): SuiteRecord | null {
  return PUBLIC_SUITES.find((suite) => suite.id === releaseId && suite.suiteManifestSha256 === manifestSha256) ?? null;
}
