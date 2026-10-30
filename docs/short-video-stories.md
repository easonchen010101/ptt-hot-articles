# 短影音故事大綱 — 早晚自動發送 Telegram

Claude 每天台北 **07:00 / 19:00**、Gemini 每天 **08:25 / 20:25**，由 GitHub Actions 分別在雲端自動產生每批 8 則 30 秒台灣短影音故事大綱，送到 Telegram。排程可能延遲，時間不是送達保證。**電腦不用開機。**

## 整體流程

```
GitHub 排程 (cron)
   │  每天台北 07:00 / 19:00 自動觸發
   ▼
讀取 latest.md（PTT 八卦板熱門文，當素材）
   ▼
Claude Opus 5.5 生成 8 則故事大綱（走訂閱，不花 API 錢）
   ▼
Python 腳本分段送到 Telegram bot
   ▼
手機收到 📱
```

Gemini 使用 `gemini-3.8-flash`、`thinkingLevel=high`；暫時性錯誤時改試 `gemini-3.6-flash`，最多 8 輪。Telegram 標頭顯示當次成功請求的模型名稱。其 cron 為 `25 0,12 * * *`（UTC）。

## 組成檔案

| 檔案 | 作用 |
|------|------|
| `.github/workflows/short-video-stories.yml` | 排程與流程定義 |
| `.github/workflows/short-video-stories-gemini.yml` | Gemini 排程與發送流程 |
| `.github/scripts/gen_gemini.py` | Gemini 模型、重試與生成 |
| `.github/prompts/short-video-prompt.txt` | 兩條排程共用的編劇規則（提示詞） |
| `.github/scripts/send_telegram.py` | 把產出純文字分段送到 Telegram |

## 逐步說明

1. **觸發** — cron `0 11,23 * * *`（UTC）= 台北早 07:00 / 晚 19:00；也可在 repo 的 **Actions → Run workflow** 手動觸發。
2. **抓素材** — 直接讀 repo 內的 `latest.md`（每 3 小時更新的 PTT 熱門文）。讀不到或異常時，提示詞會讓 Claude 改為「自由發揮」。
3. **生成** — runner 安裝 Claude Code CLI，執行
   `claude -p --model claude-opus-5-5 --effort max --allowedTools "" --output-format text`，
   認證靠 secret `CLAUDE_CODE_OAUTH_TOKEN`（`claude setup-token` 產生、走訂閱）。
4. **送 Telegram** — `send_telegram.py` 純文字分段（按行拆分，每段最多 3800 字，另加標頭；可能跨段拆開故事），靠 `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 直接打 Bot API。

## GitHub Secrets（已設定）

| Secret | 用途 |
|--------|------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude 訂閱認證（**約 2027/05 到期**，需重跑 `claude setup-token` 更新） |
| `GEMINI_API_KEY` | Gemini API 認證 |
| `TELEGRAM_BOT_TOKEN` | bot 發訊息 |
| `TELEGRAM_CHAT_ID` | 聊天室 ID |

## 為什麼用 GitHub Actions

原本評估 Claude 雲端排程（CCR），但其 sandbox 有網路白名單，**會擋掉 `api.telegram.org`**（GitHub raw 可連、Telegram 回 HTTP 403）。GitHub Actions runner 無此限制，故改用它送 Telegram；生成仍走訂閱、不花付費 API。

> 備註：2026-06-15 起 `claude -p` 在訂閱方案改吃獨立的 Agent SDK 月額度（用量小通常無感）。

## 要調整時

| 想改什麼 | 改哪裡 |
|----------|--------|
| 故事風格、則數 | `.github/prompts/short-video-prompt.txt` |
| 早晚時間 | workflow 的 `cron`（UTC = 台北 −8） |
| 換模型 | Claude workflow 的 `--model` 與標頭；Gemini 腳本的 `MODELS` |
| 手動跑一次 | repo → Actions → Run workflow |
| 除錯看 log | repo → Actions → 點該次 run |
