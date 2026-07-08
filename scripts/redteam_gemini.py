"""Send the site-design red-team brief to Gemini 3.1 Pro and save its critique.
Stdlib-only. Resolves the API key from env or the local keys file; never prints the key.
"""
import os, sys, json, re, pathlib, urllib.request, urllib.error

REPO = pathlib.Path(r"C:\Users\Michael\local-bench")
BRIEF = REPO / "docs" / "foundations" / "site-redteam-brief.md"
OUTDIR = REPO / "docs" / "foundations" / "redteam"
MODEL = "gemini-3.1-pro-preview"


def get_key():
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v.strip()
    try:
        txt = open(r"C:\Users\Michael\Desktop\API keys.txt", encoding="utf-8", errors="ignore").read()
    except OSError:
        return None
    m = re.search(r"AIza[0-9A-Za-z_\-]{20,}", txt)
    return m.group(0) if m else None


def main():
    key = get_key()
    if not key:
        print("ERROR: no Gemini API key (env GEMINI_API_KEY/GOOGLE_API_KEY or keys-file AIza...)")
        return 1
    brief = BRIEF.read_text(encoding="utf-8")
    prompt = brief + "\n\nProduce your critique now, following Section 7's output contract exactly."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 16384, "temperature": 0.7},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        # error body is the API's JSON error, not the key
        print("HTTP", e.code, e.read().decode("utf-8", "ignore")[:600])
        return 1
    except Exception as e:
        print("ERR", repr(e))
        return 1
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        print("PARSE-ERR", json.dumps(data)[:900])
        return 1
    if not text.strip():
        print("EMPTY response; finishReason=", data.get("candidates", [{}])[0].get("finishReason"))
        return 1
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "gemini-critique.md").write_text(text, encoding="utf-8")
    print(f"OK wrote {len(text)} chars to gemini-critique.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
