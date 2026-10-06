#!/usr/bin/env python3
"""呼叫 Gemini，依提示詞 + latest.md 素材產出短影音故事，寫到 stories.md。

Google 端塞車（503/斷線）時輪流換模型、每輪之間拉長間隔再試，避免該時段整條漏送。
環境變數：GEMINI_API_KEY；成功後把實際用到的模型寫進 $GITHUB_ENV 的 TG_MODEL_LABEL。
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request

# 每一輪依序嘗試：排前面的優先，塞車就換下一個
MODELS = ("gemini-3.7-flash", "gemini-3.6-flash")
# 思考深度：low / medium / high（3.x Flash 預設 medium）
THINKING_LEVEL = "high"
PROMPT_FILE = ".github/prompts/short-video-prompt.txt"
MATERIAL_FILE = "latest.md"
OUT_FILE = "stories.md"
# Google 側過載（503）/ 限流（429）/ 斷線屬暫時性錯誤，等一下或換模型可能就好
RETRY_STATUS = (429, 500, 502, 503, 504)
# 每輪之間等幾分鐘（8 輪、最多約 41 分鐘）。2026-09 中起免費層常態塞車，
# 原本 80 秒內連打 3 次常常全滅；拉長間隔才抽得到不同時段的空檔。
# 免費層每個模型約 20 次/天（503 可能也算），早晚兩次 × 8 輪 = 16 次以內。
ROUND_WAITS_MIN = (1, 2, 4, 6, 8, 10, 10)


class Transient(Exception):
    """暫時性錯誤（塞車/限流/斷線），晚點或換模型可能就好。"""


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


def reason(detail):
    """從 Google 錯誤回應取出 message；不是 JSON 就給原文開頭。"""
    try:
        return json.loads(detail)["error"]["message"][:200]
    except (ValueError, KeyError, TypeError):
        return detail[:200]


def call(model, prompt):
    """打一次 API。暫時性錯誤丟 Transient；設定類錯誤（4xx）直接結束。"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": THINKING_LEVEL}},
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
        % model,
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
            # 設定寫錯不該被換模型、重試蓋掉，立刻停下來把原因印出來
            raise SystemExit("Gemini API HTTP %s（%s）: %s" % (e.code, model, detail))
        raise Transient("HTTP %s %s" % (e.code, reason(detail)))
    # OSError 涵蓋 URLError/TimeoutError/連線被重設；HTTPException 涵蓋
    # RemoteDisconnected（Google 直接斷線，urllib 不會包成 URLError）
    except (OSError, http.client.HTTPException) as e:
        raise Transient("連線錯誤 %r" % e)


def generate(prompt):
    """一輪把 MODELS 各試一次，整輪塞車就等一下再來；回傳 (model, 回應)。"""
    start = time.monotonic()
    rounds = len(ROUND_WAITS_MIN) + 1
    for n, wait in enumerate(ROUND_WAITS_MIN + (None,), 1):
        for model in MODELS:
            try:
                return model, call(model, prompt)
            except Transient as e:
                # flush：Actions 的 stdout 有緩衝，不 flush 要等整支跑完才看得到
                print("[第 %d/%d 輪・%.0f 分] %s：%s"
                      % (n, rounds, (time.monotonic() - start) / 60, model, e),
                      flush=True)
        if wait is not None:
            print("   整輪都塞車，%d 分鐘後再試" % wait, flush=True)
            time.sleep(wait * 60)
    raise SystemExit("Google 端持續塞車：%d 輪、約 %.0f 分鐘內 %s 全部失敗"
                     % (rounds, (time.monotonic() - start) / 60, "、".join(MODELS)))


def main():
    model, d = generate(build_prompt())

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
    # 順便報則數：提示詞要 8 則，少了要能從 log 一眼看出來
    print("model=%s; %d 則、%d chars to %s; tokens: %s"
          % (model, text.count("【標題】"), len(text), OUT_FILE, um))
    # 讓 Telegram 標頭顯示「實際」用到的模型，退到備援時不會標錯
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("TG_MODEL_LABEL=%s\n" % label(model))
    # 印出開頭，方便從 Actions log 直接檢查產出品質（Claude 那條也有做）
    print("===== head =====\n" + text[:600])


if __name__ == "__main__":
    main()
