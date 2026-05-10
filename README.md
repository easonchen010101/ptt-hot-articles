# PTT 八卦版熱門文章自動抓取

每 6 小時自動抓取 PTT 八卦版推文數 ≥ 20 的文章，覆寫到 `latest.md`。
專為「給其他 AI 讀取、發想短影音題材」而設計。

## 給 AI 用的 Raw URL

```
https://raw.githubusercontent.com/easonchen010101/ptt-hot-articles/main/latest.md
```

把這個 URL 丟給 ChatGPT / Gemini / Claude，搭配以下 prompt：

> 請讀取以下網址的內容，根據裡面的 PTT 熱門文章，幫我發想 5 個適合做短影音的題材，每個題材包含：標題、開頭吸睛句、3 個重點、結尾 CTA。
> https://raw.githubusercontent.com/easonchen010101/ptt-hot-articles/main/latest.md

## 設定參數

編輯 `scraper.py` 頂端的常數：

| 參數 | 預設 | 說明 |
|------|------|------|
| `MIN_PUSH` | 20 | 推文數門檻 |
| `PAGES_TO_SCAN` | 10 | 往前掃幾頁找熱門文 |
| `CONTENT_MAX_CHARS` | 2000 | 單篇內文最長字數（避免檔案太大） |
| `TOP_PUSHES` | 10 | 每篇保留前 N 則推文 |

執行頻率改在 `.github/workflows/scrape.yml` 的 `cron` 設定。

## 本機測試

```bash
pip install -r requirements.txt
python scraper.py
# 看看 latest.md
```

## 部署步驟

1. 在 GitHub 建立 **public** repo `ptt-hot-articles`
2. 把這個資料夾推上去：
   ```bash
   cd ptt-hot-articles
   git init
   git add .
   git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/easonchen010101/ptt-hot-articles.git
   git push -u origin main
   ```
3. 到 repo 的 **Settings → Actions → General → Workflow permissions** 確認勾選 **Read and write permissions**
4. 到 **Actions** 分頁手動跑一次 `Scrape PTT Hot Articles` 確認沒問題
5. 之後每 6 小時自動更新

## 注意事項

- `cron` 在免費帳號的非尖峰時段可能延遲幾分鐘到幾十分鐘，正常現象。
- 若連續多日沒人 push（repo 看起來「閒置」），GitHub 可能暫停排程；隨便 commit 一下就會恢復。
- repo 永遠只保留最新一份內容，但 git 歷史會累積——純文字一年也才幾 MB，可忽略。
