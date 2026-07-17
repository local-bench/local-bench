// Reference: mirror of web/functions/_lib/submission-canonical.ts canonicalJson
function canonicalJson(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  return "{" + Object.keys(value).sort().filter((k) => value[k] !== undefined).map((k) => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") + "}";
}
const crypto = require("crypto");
const v1 = {
  zeta: [0.0, 1.0, 0.07692307692307693, 1e16, 1e-7, null, true, false],
  alpha: { nested: { rate: 0.0, count: 1311, label: "a\"b\\c\nend\u001f" } },
  Beta: "unicode é中文 raw",
  empty_obj: {},
  empty_arr: [],
};
const s1 = canonicalJson(v1);
console.log("V1_CANON=" + JSON.stringify(s1));
console.log("V1_SHA=" + crypto.createHash("sha256").update(Buffer.from(s1, "utf8")).digest("hex"));
const v2 = { rate: 0.0, score: 73.75, n: 400, ok: true, tag: "x" };
const s2 = canonicalJson(v2);
console.log("V2_CANON=" + s2);
console.log("V2_SHA=" + crypto.createHash("sha256").update(Buffer.from(s2, "utf8")).digest("hex"));
