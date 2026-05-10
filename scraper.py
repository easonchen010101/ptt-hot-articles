#!/usr/bin/env python3
"""PTT 八卦版熱門文章抓取器。"""

import re
import time
from datetime import datetime, timedelta, timezone

from curl_cffi import requests
from bs4 import BeautifulSoup

PTT_BASE = "https://www.ptt.cc"
BOARD_URL = f"{PTT_BASE}/bbs/Gossiping/index.html"
COOKIES = {"over18": "1"}

MIN_PUSH = 20
PAGES_TO_SCAN = 10
CONTENT_MAX_CHARS = 2000
TOP_PUSHES = 10
REQUEST_INTERVAL = 0.4
MAX_RETRIES = 3


def fetch(url: str):
    """偽裝成 Chrome 取得網頁，含重試。"""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                url,
                cookies=COOKIES,
                impersonate="chrome",
                timeout=20,
            )
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  抓取失敗（第 {attempt + 1}/{MAX_RETRIES} 次）：{e}，{wait}s 後重試")
            time.sleep(wait)
    raise last_err


def parse_push_count(text: str) -> int:
    """把推文數欄位文字（如 5、爆、X1）轉成整數。"""
    text = (text or "").strip()
    if not text:
        return 0
    if text == "爆":
        return 100
    if text.startswith("X"):
        rest = text[1:]
        if rest == "X":
            return 1000
        if rest.isdigit():
            return 100 + int(rest) * 10
    if text.lstrip("-").isdigit():
        return int(text)
    return 0


def get_article_list(url: str):
    r = fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")

    articles = []
    for ent in soup.select("div.r-ent"):
        title_a = ent.select_one("div.title a")
        if not title_a:
            continue  # 已刪除

        nrec_span = ent.select_one("div.nrec span")
        nrec_text = nrec_span.text if nrec_span else ""

        articles.append({
            "title": title_a.text.strip(),
            "url": PTT_BASE + title_a["href"],
            "push": parse_push_count(nrec_text),
            "push_text": nrec_text.strip() or "0",
            "author": ent.select_one("div.author").text.strip(),
            "date": ent.select_one("div.date").text.strip(),
        })

    prev_link = None
    for btn in soup.select("a.btn.wide"):
        if "上頁" in btn.text:
            prev_link = PTT_BASE + btn["href"]
            break

    return articles, prev_link


def get_article_content(url: str):
    r = fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.select_one("#main-content")
    if not main:
        return None, []

    pushes = []
    for p in main.select("div.push"):
        tag = p.select_one("span.push-tag")
        userid = p.select_one("span.push-userid")
        content = p.select_one("span.push-content")
        if not (tag and userid and content):
            continue
        pushes.append({
            "tag": tag.text.strip(),
            "user": userid.text.strip(),
            "content": content.text.strip().lstrip(":").strip(),
        })

    for el in main.select(
        "div.article-metaline, div.article-metaline-right, div.push"
    ):
        el.decompose()
    text = main.get_text("\n").strip()
    text = re.split(r"※ 發信站", text)[0].strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text, pushes


def main():
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M (UTC+8)")
    print(f"[{now}] 開始抓取...")

    hot = []
    url = BOARD_URL
    pages = 0
    while pages < PAGES_TO_SCAN and url:
        articles, prev_link = get_article_list(url)
        for a in articles:
            if a["push"] >= MIN_PUSH:
                hot.append(a)
        pages += 1
        url = prev_link
        time.sleep(REQUEST_INTERVAL)

    # 去重（多頁可能重複）
    seen = set()
    deduped = []
    for a in hot:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        deduped.append(a)
    hot = sorted(deduped, key=lambda x: x["push"], reverse=True)

    print(f"掃描 {pages} 頁，找到 {len(hot)} 篇推文數 ≥ {MIN_PUSH} 的文章")

    for a in hot:
        try:
            content, pushes = get_article_content(a["url"])
            a["content"] = content
            a["pushes"] = pushes[:TOP_PUSHES]
            time.sleep(REQUEST_INTERVAL)
        except Exception as e:
            print(f"  抓取內文失敗 {a['url']}: {e}")
            a["content"] = None
            a["pushes"] = []

    lines = [
        "# PTT 八卦版熱門文章",
        "",
        f"> **更新時間**：{now}　|　**篩選**：推文數 ≥ {MIN_PUSH}　"
        f"|　**掃描頁數**：{pages}　|　**找到**：{len(hot)} 篇",
        "",
        "本檔案由 GitHub Actions 每 6 小時自動更新，永遠只保留最新一份。",
        "",
        "---",
        "",
    ]

    if not hot:
        lines.append("_目前沒有符合條件的文章_")
    else:
        for i, a in enumerate(hot, 1):
            lines.append(f"## {i}. {a['title']}")
            lines.append("")
            lines.append(f"- **推文數**：{a['push_text']}")
            lines.append(f"- **作者**：{a['author']}")
            lines.append(f"- **日期**：{a['date']}")
            lines.append(f"- **連結**：{a['url']}")
            lines.append("")
            if a.get("content"):
                lines.append("### 內文")
                lines.append("")
                content = a["content"]
                if len(content) > CONTENT_MAX_CHARS:
                    content = content[:CONTENT_MAX_CHARS] + "\n\n（內文過長，已截斷）"
                lines.append(content)
                lines.append("")
            if a.get("pushes"):
                lines.append("### 熱門推文")
                lines.append("")
                for p in a["pushes"]:
                    lines.append(f"- {p['tag']} **{p['user']}**：{p['content']}")
                lines.append("")
            lines.append("---")
            lines.append("")

    with open("latest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("已寫入 latest.md")


if __name__ == "__main__":
    main()
