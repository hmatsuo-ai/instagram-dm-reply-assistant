# 初期設定（最短手順）

**標準構成: LINE Messaging API がこのサーバの `/webhook/line` に直接届く（GAS 不要）。**  
バックエンドは **RAG + Gemini API**（OpenAI は任意フォールバック）。  
Vercel 利用時は **`VERCEL_DEPLOY.md`** も参照。

## 0. 前提

- Python 3.10 以上想定
- LINE Webhook 用の **HTTPS の公開 URL**（Vercel・トンネル・リバースプロキシなど）

## 1. 依存インストール

```bash
pip install -r requirements-bot.txt
```

## 2. 環境ファイル

```bash
python scripts/init_env.py
```

`.env` を開き、次を記入:

| 変数 | 説明 |
|------|------|
| `LINE_CHANNEL_SECRET` | LINE Developers のチャネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | 長期チャネルアクセストークン |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) 等（推奨） |
| `ALLOW_DIRECT_LINE_WEBHOOK` | 既定 `true`（そのままでよい） |

任意: `LINE_ALLOWED_USER_IDS`、`INTERNAL_WEBHOOK_SECRET`（`/internal/suggest-replies` を別経路から叩くときのみ）、`OPENAI_API_KEY`。

## 3. RAG データ（過去 DM を学習させる場合）

1. `メッセージ履歴/messages/inbox` に JSON を配置
2. `config/rag_business_patterns.json` を確認
3. `python scripts/build_rag_chunks.py`

## 4. 設定確認

```bash
python scripts/check_setup.py
```

`[NG]` が無いことを確認。

## 5. サーバ起動（自営 PC）

```bash
python run_server.py
```

公開 URL の例: `https://あなたのドメイン/health` で `line_secret_configured: true` を確認。

## 6. LINE Developers

1. [LINE Developers](https://developers.line.biz/) → Messaging API → **Webhook URL**  
   **`https://あなたの公開ホスト/webhook/line`**（末尾スラッシュなし）
2. **Verify** → **Use webhook をオン**
3. Bot にメッセージを送り、返信案が返るか確認

## 7. Vercel でホストする

**`VERCEL_DEPLOY.md`** に環境変数・デプロイ・Webhook の細かい手順あり。  
`LINE_CHANNEL_*` と `GEMINI_API_KEY` は **Vercel の Environment Variables** に設定する。

## 任意: Google Apps Script（中継）

LINE 秘密をサーバに置きたくない場合だけ `gas/LineRelay.gs` を使い、`ALLOW_DIRECT_LINE_WEBHOOK=false` と `INTERNAL_WEBHOOK_SECRET` で `/internal/suggest-replies` に寄せる。**通常は不要。**

## よくあるつまずき

- Webhook は **`https`** 必須。`/webhook/line` までパスを合わせる
- `LINE_CHANNEL_SECRET` が `.env`（または Vercel）と LINE コンソールで一致しているか
