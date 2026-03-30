# Vercel デプロイ手順（細かい流れ）

**LINE Webhook は GAS を使わず、Vercel 上の `POST /webhook/line` に直接指定します。**

ルートの `app.py` で FastAPI を公開します。

---

## 事前に用意するもの

| もの | 用途 |
|------|------|
| **GitHub 等** | Vercel とリポジトリ連携 |
| **Vercel アカウント** | [vercel.com](https://vercel.com) |
| **LINE Developers** のチャネルシークレット・長期トークン | 環境変数に設定 |
| **Gemini API キー** | [Google AI Studio](https://aistudio.google.com/apikey) 等 |
| **`output/rag_chunks.jsonl`** | ローカルで `build_rag_chunks.py` 後、**Git にコミット**推奨 |

---

## A. ローカルでそろえる

1. リポジトリルートへ `cd`
2. 任意: `pip install -r requirements.txt`
3. RAG: `python scripts/build_rag_chunks.py` → `output/rag_chunks.jsonl` を push
4. **`.env` はコミットしない**

---

## B. Vercel でプロジェクト作成

1. [vercel.com/new](https://vercel.com/new) でリポジトリをインポート
2. Root Directory はそのまま
3. Build Command は空で可（`requirements.txt` でインストール）
4. 先に **環境変数**（次節）を入れてから Deploy してもよい

---

## C. 環境変数（Settings → Environment Variables）

**Production**（必要なら Preview）に追加:

| Name | 必須 | 説明 |
|------|------|------|
| `LINE_CHANNEL_SECRET` | はい | LINE Developers |
| `LINE_CHANNEL_ACCESS_TOKEN` | はい | 長期トークン |
| `GEMINI_API_KEY` | 推奨 | |
| `ALLOW_DIRECT_LINE_WEBHOOK` | はい | **`true`** |

**任意**

| Name | 説明 |
|------|------|
| `GEMINI_MODEL` | 既定で可 |
| `LINE_ALLOWED_USER_IDS` | カンマ区切り |
| `RAG_TOP_K` | |
| `OPENAI_API_KEY` | Gemini が無いとき |
| `INTERNAL_WEBHOOK_SECRET` | `/internal/suggest-replies` を使う場合のみ |

Save 後、変数を変えたら **Redeploy**。

---

## D. デプロイと確認

1. **Deploy**
2. ドメインを控える（例: `https://xxx.vercel.app`）
3. ブラウザで **`https://ドメイン/health`**  
   - `ok: true`  
   - `direct_line_webhook_allowed: true`  
   - `line_secret_configured: true`  
   - `line_token_configured: true`  
   - `llm_provider` が `gemini` 等  

ログは Deployments → 該当ビルド → **Logs**。

---

## E. LINE Developers

1. **Webhook URL** を  
   **`https://ドメイン.vercel.app/webhook/line`**  
   に設定（`https`・末尾スラッシュなし）
2. **Verify** → **Use webhook オン**
3. Bot に送信して動作確認

---

## F. 制限メモ

- **`maxDuration: 60`** はプラン上限を超えない（無料枠は短いことがある）
- バンドルは **約 500MB 未満**に

---

## チェックリスト

- [ ] `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` / `GEMINI_API_KEY` / `ALLOW_DIRECT_LINE_WEBHOOK=true`
- [ ] `/health` で LINE 関連が true
- [ ] Webhook URL が `/webhook/line`
- [ ] RAG 用 JSONL をデプロイに含めた（任意だが推奨）

詳細背景: `SETUP.md`・`LINEスカウト返信支援Bot_仕様書.md`
