#!/usr/bin/env python3
"""呼叫 Gemini，依提示詞 + latest.md 素材產出短影音故事，寫到 stories.md。

主模型塞車（503/斷線）時自動退到備援模型，避免該時段整條漏送。
環境變數：GEMINI_API_KEY；成功後把實際用到的模型寫進 $GITHUB_ENV 的 TG_MODEL_LABEL。
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request

# 依序嘗試：主模型塞車就退到下一個
MODELS = ("gemini-3.7-flash", "gemini-3.6-flash")
# 思考深度：low / medium / high（3.x Flash 預設 medium）
THINKING_LEVEL = "high"
PROMPT_FILE = ".github/prompts/short-video-prompt.txt"
MATERIAL_FILE = "latest.md"
OUT_FILE = "stories.md"
# Google 側過載（503）/ 限流（429）會整條掛掉害該時段漏送，所以退避重試
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRY_WAITS = (20, 60)


class Overloaded(Exception):
    """該模型重試用盡仍是暫時性錯誤，可以換下一個模型。"""


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


def label(model):
    """gemini-3.7-flash -> Gemini 3.7 Flash（給 Telegram 標頭用）"""
    return " ".join(w.capitalize() if w.isalpha() else w for w in model.split("-"))


def call(model, prompt):
    """打一個模型，暫時性錯誤退避重試；重試用盡丟 Overloaded。"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": THINKING_LEVEL}},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
        % model
    )
    for attempt, wait in enumerate(RETRY_WAITS + (None,), 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 沒有這段的話 4xx 只會看到 "HTTP Error 400"，看不到真正原因
            detail = e.read().decode("utf-8", "replace")[:1000]
            if e.code not in RETRY_STATUS:
                raise SystemExit("Gemini API HTTP %s（%s）: %s" % (e.code, model, detail))
            if wait is None:
                raise Overloaded("%s 重試用盡，最後 HTTP %s" % (model, e.code))
            print("[%s] 第 %d 次失敗 HTTP %s，%d 秒後重試：%s" % (model, attempt, e.code, wait, detail[:200]))
        # OSError 涵蓋 URLError/TimeoutError/連線被重設；HTTPException 涵蓋
        # RemoteDisconnected（Google 直接斷線，urllib 不會包成 URLError）
        except (OSError, http.client.HTTPException) as e:
            if wait is None:
                raise Overloaded("%s 重試用盡，最後連線錯誤 %r" % (model, e))
            print("[%s] 第 %d 次連線失敗（%r），%d 秒後重試" % (model, attempt, e, wait))
        time.sleep(wait)


def main():
    prompt = build_prompt()
    last = None
    for model in MODELS:
        try:
            d = call(model, prompt)
        except Overloaded as e:
            print("⚠️ %s；改用下一個模型" % e)
            last = e
            continue
        break
    else:
        raise SystemExit("所有模型都不可用：%s" % last)

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
    print("model=%s; generated %d chars to %s; tokens: %s" % (model, len(text), OUT_FILE, um))
    # 讓 Telegram 標頭顯示「實際」用到的模型，退到備援時不會標錯
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("TG_MODEL_LABEL=%s\n" % label(model))
    # 印出開頭，方便從 Actions log 直接檢查產出品質（Claude 那條也有做）
    print("===== head =====\n" + text[:600])


if __name__ == "__main__":
    main()
