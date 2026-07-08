"""Send the site-design red-team brief to Qwen 3.7 Max (DashScope, OpenAI-compatible).
Stdlib-only. Tries intl + China endpoints and several max-tier model slugs until one works.
Key resolved from env DASHSCOPE_API_KEY/QWEN_API_KEY, else a labelled line in the keys file.
Never prints the key.
"""
import os, sys, json, re, pathlib, urllib.request, urllib.error

REPO = pathlib.Path(r"C:\Users\Michael\local-bench")
BRIEF = REPO / "docs" / "foundations" / "site-redteam-brief.md"
OUTDIR = REPO / "docs" / "foundations" / "redteam"
ENDPOINTS = [
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
]
MODELS = ["qwen3.7-max", "qwen-max-latest", "qwen3-max", "qwen-max", "qwen-plus"]


def get_key():
    for v in ("DASHSCOPE_API_KEY", "QWEN_API_KEY"):
        if os.environ.get(v):
            return os.environ[v].strip()
    try:
        for line in open(r"C:\Users\Michael\Desktop\API keys.txt", encoding="utf-8", errors="ignore"):
            if re.search(r"qwen|dashscope", line, re.I):
                m = re.search(r"sk-[0-9A-Za-z]{20,}", line)
                if m:
                    return m.group(0)
    except OSError:
        pass
    return None


def main():
    key = get_key()
    if not key:
        print("ERROR: no Qwen key (env DASHSCOPE_API_KEY or labelled keys-file line)")
        return 1
    brief = BRIEF.read_text(encoding="utf-8")
    prompt = brief + "\n\nProduce your critique now, following Section 7's output contract exactly."
    last = None
    for ep in ENDPOINTS:
        for model in MODELS:
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8192,
                "temperature": 0.7,
            }
            req = urllib.request.Request(
                ep, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.load(r)
                text = data["choices"][0]["message"].get("content", "")
                if text and text.strip():
                    OUTDIR.mkdir(parents=True, exist_ok=True)
                    host = ep.split("/")[2]
                    (OUTDIR / "qwen-critique.md").write_text(
                        f"<!-- model: {model} @ {host} -->\n\n" + text, encoding="utf-8")
                    print(f"OK model={model} endpoint={host} wrote {len(text)} chars")
                    return 0
                last = f"{model}@{ep.split('/')[2]}: empty content"
            except urllib.error.HTTPError as e:
                last = f"{model}@{ep.split('/')[2]}: HTTP {e.code} {e.read().decode('utf-8','ignore')[:200]}"
            except Exception as e:
                last = f"{model}@{ep.split('/')[2]}: {repr(e)[:200]}"
    print("FAILED all endpoint/model combos. last:", last)
    return 1


if __name__ == "__main__":
    sys.exit(main())
