#!/usr/bin/env python3
"""呼叫 Gemini 3.7 Flash，依提示詞 + latest.md 素材產出短影音故事，寫到 stories.md。

環境變數：GEMINI_API_KEY
"""
import json
import os
import time
import urllib.error
import urllib.request

MODEL = "gemini-3.7-flash"
# 思考深度：low / medium / high（3.7 Flash 預設 medium）
THINKING_LEVEL = "high"
PROMPT_FILE = ".github/prompts/short-video-prompt.txt"
MATERIAL_FILE = "latest.md"
OUT_FILE = "stories.md"
# Google 側過載（503）/ 限流（429）會整條掛掉害該時段漏送，所以退避重試
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRY_WAITS = (20, 60, 120, 240)


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
    d = None
    for attempt, wait in enumerate(RETRY_WAITS + (None,), 1):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            # 沒有這段的話 4xx 只會看到 "HTTP Error 400"，看不到真正原因
            detail = e.read().decode("utf-8", "replace")[:1000]
            if e.code in RETRY_STATUS and wait is not None:
                print("第 %d 次失敗 HTTP %s，%d 秒後重試：%s" % (attempt, e.code, wait, detail[:200]))
                time.sleep(wait)
                continue
            raise SystemExit("Gemini API HTTP %s: %s" % (e.code, detail))
        except (urllib.error.URLError, TimeoutError) as e:
            if wait is None:
                raise SystemExit("Gemini API 連線失敗：%s" % e)
            print("第 %d 次連線失敗（%s），%d 秒後重試" % (attempt, e, wait))
            time.sleep(wait)

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
