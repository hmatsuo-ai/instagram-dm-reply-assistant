# 初期設定（最短手順）

推奨構成: **Google Apps Script（LINE Messaging API 入口）** ＋ **この PC 上の Python サーバ（RAG + Gemini API）**。  
（Gemini 未設定時のみ OpenAI 互換 API にフォールバック可能）  
詳細仕様は `LINEスカウト返信支援Bot_仕様書.md` を参照。

## 0. 前提

- Python 3.10 以上想定
- LINE から届く Webhook 用に **HTTPS の公開 URL** が必要  
  - **自営 PC + トンネル**、または下記の **Vercel** など

## 1. 依存インストール

リポジトリのルートで:

```bash
pip install -r requirements-bot.txt
```

## 2. 環境ファイル

```bash
python scripts/init_env.py
```

- `.env` が作成され、`INTERNAL_WEBHOOK_SECRET` が自動で入ります。
- エディタで `.env` を開き、**`GEMINI_API_KEY=`** のあとに API キーを貼る（[Google AI Studio](https://aistudio.google.com/apikey) などで発行。**推奨**）。未設定でも起動は可能ですが、返信案は定型フォールバックになります。
- 任意: `GEMINI_MODEL`（既定 `gemini-2.0-flash`）。Gemini を使わず OpenAI のみにする場合は `OPENAI_API_KEY` のみ設定。

## 3. RAG データ（過去 DM を学習させる場合）

1. `メッセージ履歴/messages/inbox` に Instagram エクスポート等の JSON を配置
2. `config/rag_business_patterns.json` で自社アカウント名のルールを確認
3. 以下を実行:

```bash
python scripts/build_rag_chunks.py
```

## 4. 設定確認

```bash
python scripts/check_setup.py
```

`[NG]` が無いことを確認してください。

## 5. サーバ起動

```bash
python run_server.py
```

トンネル等で `https://あなたの公開ドメイン` → この PC の `PORT`（既定 8000）に転送します。  
ブラウザまたは `curl` で次を確認:

- `https://あなたの公開ドメイン/health`  
  → `internal_api_enabled: true` になること

## 6. GAS（LINE → サーバ → 返信）

1. [Google Apps Script](https://script.google.com/) で新規プロジェクトを作る  
2. `gas/LineRelay.gs` の内容を貼り付け  
3. **プロジェクトの設定 → スクリプト プロパティ** に次を追加（値はすべて手入力。コードに書かない）:

| プロパティ | 値の例 |
|------------|--------|
| `LINE_CHANNEL_SECRET` | LINE Developers のチャネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | 長期チャネルアクセストークン |
| `BACKEND_SUGGEST_URL` | `https://あなたの公開ドメイン/internal/suggest-replies` |
| `INTERNAL_WEBHOOK_SECRET` | **`.env` の `INTERNAL_WEBHOOK_SECRET` と完全に同じ** |
| `WEBHOOK_QUERY_TOKEN` | 長いランダム文字列（推奨） |
| `LINE_ALLOWED_USER_IDS` | （任意）許可する userId をカンマ区切り |

4. **デプロイ → 新しいデプロイ → 種類: ウェブアプリ**  
   - 次のユーザーとして実行: **自分**  
   - アクセス: **全人**  
5. 表示された **ウェブアプリ URL** をコピーし、末尾に `?token=（WEBHOOK_QUERY_TOKEN と同じ）` を付ける  
6. [LINE Developers](https://developers.line.biz/) の Messaging API で **Webhook URL** にその URL を設定し、**Verify** → **Use webhook をオン**

## 7. Vercel でホストする（トンネル代替）

**画面操作・環境変数・チェックリストの細かい手順は `VERCEL_DEPLOY.md` を参照。**

[FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi) の想定どおり、リポジトリ直下の **`app.py`** が `bot_server.main.app` を公開します。依存はルートの **`requirements.txt`** → `requirements-bot.txt` を読み込みます。**`vercel.json`** でインストールコマンド・関数の `maxDuration` / メモリを指定しています。

### 手順

1. **RAG ファイルをデプロイに含める**  
   - ローカルで `python scripts/build_rag_chunks.py` 済みの **`output/rag_chunks.jsonl`** を Git にコミットする（または CI のビルドで生成）。  
   - 巨大な生履歴 `メッセージ履歴/` は **`.vercelignore` でバンドルから除外**済み。チャンク JSONL だけ載せる想定。

2. **Vercel にプロジェクトをインポート**（Git 連携または `vercel deploy`）。  
   - Framework は自動検出（Python / FastAPI）でよいことが多い。

3. **Project → Settings → Environment Variables** に最低限これを設定:

   | 名前 | 説明 |
   |------|------|
   | `INTERNAL_WEBHOOK_SECRET` | GAS のスクリプトプロパティと**同一** |
   | `GEMINI_API_KEY` | （推奨）Google AI 等 |
   | `ALLOW_DIRECT_LINE_WEBHOOK` | `false`（GAS のみ受けたい場合） |
   | `RAG_CHUNKS_PATH` | 通常は未設定で可（既定 `output/rag_chunks.jsonl`） |

   ※ Vercel には **LINE のチャネルシークレット／長期トークンは書かない**（GAS プロパティのみ）。

4. デプロイ後、`https://（Vercel のドメイン）/health` で `ok`・`internal_api_enabled: true`・`llm_provider` を確認。

5. **GAS の `BACKEND_SUGGEST_URL`** を  
   `https://（Vercel のドメイン）/internal/suggest-replies` に更新。  
   `INTERNAL_WEBHOOK_SECRET` も Vercel 側の値と一致させる。

### 注意（仕様の制約）

| 項目 | 内容 |
|------|------|
| **実行時間** | サーバレスには**上限時間**がある。Gemini が遅いとタイムアウトする場合は Vercel の **maxDuration**（プラン依存）を伸ばす・軽いモデルにする等。 |
| **バンドルサイズ** | Python 関数は **非圧縮で約 500MB 上限**。不要データは `.vercelignore` / `vercel.json` の `excludeFiles` で省く。 |
| **コールドスタート** | しばらく誰も使わないと初回だけ遅くなりがち。 |
| **ディスク** | 実行中のローカル書き込みは基本的に持たない（読み取り中心の本コードはその前提に近い）。 |

常設 PC が不要になる反面、**長時間 LLM・巨大 RAG** はオンプレ／常時起動 VM の方が向くことがあります。

## よくあるつまずき

- GAS の `INTERNAL_WEBHOOK_SECRET` とサーバ側（`.env` または Vercel の環境変数）が **1 文字でも違う**と 401 になる  
- `BACKEND_SUGGEST_URL` は **https**、パス末尾まで `/internal/suggest-replies` と合わせる  
- 仕様書 §3.3（トンネル）と §6.6 も参照（Vercel 利用時はドメインが Vercel の URL になるだけ）
