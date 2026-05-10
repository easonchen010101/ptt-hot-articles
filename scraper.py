#!/usr/bin/env python3
"""PTT 八卦版熱門文章抓取器：過去 N 小時、推文數 ≥ X 的文章。"""

import re
import time
from datetime import datetime, timedelta, timezone

from curl_cffi import requests
from bs4 import BeautifulSoup

PTT_BASE = "https://www.ptt.cc"
BOARD_URL = f"{PTT_BASE}/bbs/Gossiping/index.html"
COOKIES = {"over18": "1"}

MIN_PUSH = 50
LOOKBACK_HOURS = 24
PAGES_TO_SCAN = 50
CONTENT_MAX_CHARS = 2000
TOP_PUSHES = 10
REQUEST_INTERVAL = 0.4
MAX_RETRIES = 3
TZ = timezone(timedelta(hours=8))


def fetch(url: str):
    """偽裝 Chrome 抓取，含重試。"""
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


def parse_post_time(value: str):
    """PTT 時間字串 'Sat May 10 14:23:45 2026' → 帶時區 datetime。"""
    try:
        dt = datetime.strptime(value.strip(), "%a %b %d %H:%M:%S %Y")
        return dt.replace(tzinfo=TZ)
    except (ValueError, AttributeError):
        return None


def get_article_list(url: str):
    r = fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")

    articles = []
    for ent in soup.select("div.r-ent"):
        title_a = ent.select_one("div.title a")
        if not title_a:
            continue

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
        return None, [], None

    post_time = None
    for metaline in main.select("div.article-metaline"):
        tag = metaline.select_one("span.article-meta-tag")
        value = metaline.select_one("span.article-meta-value")
        if tag and value and tag.text.strip() == "時間":
            post_time = parse_post_time(value.text)
            break

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

    return text, pushes, post_time


def main():
    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)
    now_str = now.strftime("%Y-%m-%d %H:%M (UTC+8)")
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M (UTC+8)")
    print(f"[{now_str}] 開始抓取")
    print(f"  條件：發文時間 ≥ {cutoff_str} 且 推文數 ≥ {MIN_PUSH}")

    # Step 1: 掃描索引頁，收集推文數達標的候選
    candidates = []
    url = BOARD_URL
    pages = 0
    while pages < PAGES_TO_SCAN and url:
        articles, prev_link = get_article_list(url)
        for a in articles:
            if a["push"] >= MIN_PUSH:
                candidates.append(a)
        pages += 1
        url = prev_link
        time.sleep(REQUEST_INTERVAL)

    # 去重
    seen = set()
    deduped = []
    for a in candidates:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        deduped.append(a)

    print(f"  掃描 {pages} 頁，{len(deduped)} 篇符合推文數，開始抓取內文…")

    # Step 2: 抓內文 + 解析時間 + 過濾
    in_window = []
    for a in deduped:
        try:
            content, pushes, post_time = get_article_content(a["url"])
            a["content"] = content
            a["pushes"] = pushes[:TOP_PUSHES]
            a["post_time"] = post_time
            if post_time and post_time >= cutoff:
                in_window.append(a)
            time.sleep(REQUEST_INTERVAL)
        except Exception as e:
            print(f"  抓取內文失敗 {a['url']}: {e}")

    in_window.sort(key=lambda x: x["push"], reverse=True)
    print(f"  過去 {LOOKBACK_HOURS} 小時內符合條件：{len(in_window)} 篇")

    # Step 3: 寫入 markdown
    lines = [
        "# PTT 八卦版熱門文章",
        "",
        f"> **更新時間**：{now_str}",
        f">",
        f"> **篩選條件**：發文時間 ≥ {cutoff_str}（過去 {LOOKBACK_HOURS} 小時）"
        f"且 推文數 ≥ {MIN_PUSH}",
        f">",
        f"> **掃描頁數**：{pages}　|　**找到**：{len(in_window)} 篇",
        "",
        f"本檔案由 GitHub Actions 自動更新，永遠只保留最新一份。",
        "",
        "---",
        "",
    ]

    if not in_window:
        lines.append("_目前沒有符合條件的文章_")
    else:
        for i, a in enumerate(in_window, 1):
            lines.append(f"## {i}. {a['title']}")
            lines.append("")
            lines.append(f"- **推文數**：{a['push_text']}")
            lines.append(f"- **作者**：{a['author']}")
            time_str = a["post_time"].strftime("%Y-%m-%d %H:%M") if a["post_time"] else a["date"]
            lines.append(f"- **發文時間**：{time_str}")
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
