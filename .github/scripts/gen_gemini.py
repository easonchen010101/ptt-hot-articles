#!/usr/bin/env python3
"""呼叫 Gemini 3.6 Flash，依提示詞 + latest.md 素材產出短影音故事，寫到 stories.md。

環境變數：GEMINI_API_KEY
"""
import json
import os
import urllib.request

MODEL = "gemini-3.6-flash"
PROMPT_FILE = ".github/prompts/short-video-prompt.txt"
MATERIAL_FILE = "latest.md"
OUT_FILE = "stories.md"


def build_prompt():
    parts = [
        open(PROMPT_FILE, encoding="utf-8").read(),
        "\n----- 以下為素材（PTT 八卦版熱門文，若內容異常或為空則自由發揮）-----\n",
    ]
    try:
        parts.append(open(MATERIAL_FILE, encoding="utf-8").read())
    except FileNotFoundError:
        parts.append("自由發揮")
    return "".join(parts)


def main():
    body = {"contents": [{"parts": [{"text": build_prompt()}]}]}
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
        % MODEL
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": os.environ["GEMINI_API_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode("utf-8"))

    if "error" in d:
        raise SystemExit("Gemini API error: " + json.dumps(d["error"])[:500])
    cand = d.get("candidates", [])
    if not cand:
        raise SystemExit("No candidates returned: " + json.dumps(d)[:500])

    text = "".join(
        p.get("text", "") for p in cand[0].get("content", {}).get("parts", [])
    )
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    um = d.get("usageMetadata", {})
    print("generated %d chars to %s; tokens: %s" % (len(text), OUT_FILE, um))


if __name__ == "__main__":
    main()
