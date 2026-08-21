#!/usr/bin/env python3
"""呼叫 Gemini 3.7 Flash，依提示詞 + latest.md 素材產出短影音故事，寫到 stories.md。

環境變數：GEMINI_API_KEY
"""
import json
import os
import urllib.error
import urllib.request

MODEL = "gemini-3.7-flash"
# 思考深度：low / medium / high（3.7 Flash 預設 medium）
THINKING_LEVEL = "high"
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
    body = {
        "contents": [{"parts": [{"text": build_prompt()}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": THINKING_LEVEL}},
    }
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
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 沒有這段的話 4xx 只會看到 "HTTP Error 400"，看不到真正原因
        raise SystemExit(
            "Gemini API HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:1000])
        )

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
    # 印出開頭，方便從 Actions log 直接檢查產出品質（Claude 那條也有做）
    print("===== head =====\n" + text[:600])


if __name__ == "__main__":
    main()
