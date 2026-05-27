#!/usr/bin/env python3
"""把產出的故事大綱分段送到 Telegram。

用法：send_telegram.py <檔案路徑>
環境變數：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
"""
import os
import sys
import time
import json
import urllib.parse
import urllib.request

LIMIT = 3800  # Telegram 單則上限約 4096，留安全邊界
HEADER = "🎬 今日短影音故事大綱（共 8 則）\n\n"


def chunk_text(text, limit):
    """以行為單位切塊，盡量不從行中間切斷；單行過長才硬切。"""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def send(token, chat_id, msg):
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError("Telegram API error: %s" % body)


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    path = sys.argv[1]

    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        text = "（本次未產生內容，請檢查 workflow log）"

    chunks = chunk_text(text, LIMIT)
    if chunks:
        chunks[0] = HEADER + chunks[0]

    for i, c in enumerate(chunks):
        send(token, chat_id, c)
        print("sent chunk %d/%d (%d chars)" % (i + 1, len(chunks), len(c)))
        time.sleep(1)
    print("done: %d message(s) sent" % len(chunks))


if __name__ == "__main__":
    main()
