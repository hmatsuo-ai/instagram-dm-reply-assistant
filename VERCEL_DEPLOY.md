# Vercel デプロイ手順（細かい流れ）

このリポジトリはルートの `app.py` で FastAPI を公開し、GAS の `BACKEND_SUGGEST_URL` から `POST /internal/suggest-replies` を受けます。

---

## 事前に用意するもの

| もの | 用途 |
|------|------|
| **GitHub（など）アカウント** | Vercel とリポジトリを連携するため |
| **Vercel アカウント** | [vercel.com](https://vercel.com)（GitHub ログインで可） |
| **Gemini API キー** | [Google AI Studio](https://aistudio.google.com/apikey) など |
| **RAG 用 `output/rag_chunks.jsonl`** | ローカルで `python scripts/build_rag_chunks.py` 実行後、**Git にコミット**する（空でも起動はするが `rag_ready` は false） |
| **GAS 用の秘密** | `INTERNAL_WEBHOOK_SECRET` を 1 本決める（Vercel と GAS の両方に**同じ文字列**） |

---

## A. ローカルで足りるものをそろえる

1. **ターミナルでリポジトリのルートに移動**する。
2. **依存の確認（任意）**  
   ```bash
   pip install -r requirements.txt
   ```
3. **RAG をビルド**（過去 DM を使う場合）  
   - `メッセージ履歴/...` に JSON を置いたうえで:  
     ```bash
     python scripts/build_rag_chunks.py
     ```
   - `output/rag_chunks.jsonl` が生成される。
4. **Git に載せる**  
   - `output/rag_chunks.jsonl` をコミットする（初回だけ `output/.gitkeep` だけでもデプロイ可。本番ではチャンクファイル推奨）。  
   - **`.env` はコミットしない**（`.gitignore` 済み）。
5. **リモートへ push**  
   - 例: `git push origin main`

---

## B. Vercel で新規プロジェクトを作る

1. ブラウザで [https://vercel.com/new](https://vercel.com/new) を開く。
2. **「Git リポジトリをインポート」**で、該当リポジトリを選ぶ。
3. **Project 名**は任意（URL の一部になる）。
4. **Framework Preset**  
   - **Other** のまま、または **FastAPI** が出ればそれでも可。  
   - **Root Directory** はリポジトリのルートのまま（変更不要）。
5. **Build & Output**（表示される場合）  
   - **Build Command**: 空、またはデフォルトのまま（Python は `requirements.txt` でインストール）。  
   - **Output Directory**: 空のまま（Static Export しない）。
6. まだ **Deploy しない**。先に **環境変数** を入れる（次節）。

---

## C. 環境変数（Settings → Environment Variables）

デプロイ前またはデプロイ後に、**Production**（および必要なら Preview）に次を追加する。

| Name | Value | 必須 |
|------|-------|------|
| `INTERNAL_WEBHOOK_SECRET` | 長いランダム文字列（例: 32byte hex）。**GAS のスクリプトプロパティと同一** | はい |
| `GEMINI_API_KEY` | Google AI Studio 等のキー | 本番推奨 |
| `ALLOW_DIRECT_LINE_WEBHOOK` | `false` | 推奨（GAS のみ受けたい場合） |

**任意**

| Name | 例 | 説明 |
|------|-----|------|
| `GEMINI_MODEL` | `gemini-2.0-flash` | 既定でよければ省略 |
| `RAG_TOP_K` | `8` | 省略可 |
| `OPENAI_API_KEY` | （秘密） | Gemini が無いときだけ使うフォールバック |

**書かないもの（Vercel には置かない）**

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`  
→ これらは **GAS のスクリプト プロパティ**のみ。

設定後、**Save**。初回または変数変更後は **Redeploy** が必要な場合があります。

---

## D. デプロイ実行

1. **Deploy** を押す（または環境変数設定後に **Redeploy**）。
2. 完了画面の **ドメイン** を控える（例: `https://line-bot-xxxx.vercel.app`）。
3. ブラウザで次を開く:  
   `https://あなたのドメイン/health`  
   - `ok: true`  
   - `internal_api_enabled: true`（`INTERNAL_WEBHOOK_SECRET` が効いている）  
   - `llm_provider: "gemini"`（キー設定済みなら）  
   を確認。

**うまくいかないとき**

- **500 / Application Error** → Vercel の **Deployments → 該当デプロイ → Logs** でビルド・実行ログを見る。
- **`internal_api_enabled: false`** → `INTERNAL_WEBHOOK_SECRET` が空、または再デプロイ前。

---

## E. Google Apps Script の更新

1. `gas/LineRelay.gs` を GAS プロジェクトに貼り付け済みであること。
2. **スクリプト プロパティ**を開く。
3. 次を **必ず Vercel と一致**させる。
   - `BACKEND_SUGGEST_URL` →  
     `https://あなたのドメイン.vercel.app/internal/suggest-replies`  
     （末尾スラッシュなし・`https`）
   - `INTERNAL_WEBHOOK_SECRET` → Vercel の **同じ値**
4. ほか `LINE_CHANNEL_*`・`WEBHOOK_QUERY_TOKEN` は従来どおり。
5. **デプロイ → ウェブアプリ**をやり直し、Webhook URL（`?token=...` 付き）を再取得したい場合は LINE 側も更新。

---

## F. LINE Developers

1. **Webhook URL** を GAS の **ウェブアプリ URL + `?token=WEBHOOK_QUERY_TOKEN`** にする。
2. **Verify** → **Use webhook をオン**。
3. Bot にテキストを送り、返信案が返るか確認。

---

## G. 制限・運用メモ

- **`vercel.json` の `maxDuration: 60`** は **プランの上限より長くは効きません**（無料枠などでは **10 秒前後**に制限されることがある）。Gemini が間に合わず 504 になる場合は **Pro 等で延長**するか、モデル・プロンプトを軽くする。
- **バンドルサイズ**はおおむね 500MB 未満に抑える。巨大なファイルは Git / `.vercelignore` で含めない。
- **環境変数を変えた**ら **再デプロイ**が必要なことが多い。

---

## ひとことチェックリスト

- [ ] `output/rag_chunks.jsonl` をビルドして push（または意図して空運用）
- [ ] Vercel に `INTERNAL_WEBHOOK_SECRET` / `GEMINI_API_KEY` / `ALLOW_DIRECT_LINE_WEBHOOK=false`
- [ ] `/health` が期待どおり
- [ ] GAS の `BACKEND_SUGGEST_URL` と `INTERNAL_WEBHOOK_SECRET` が Vercel と一致
- [ ] LINE Webhook URL を Verify

詳しい構成の背景は `SETUP.md` と `LINEスカウト返信支援Bot_仕様書.md` を参照してください。
