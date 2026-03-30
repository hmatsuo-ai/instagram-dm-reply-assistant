"""
初期設定のチェック（GAS 中継＋自営サーバ想定）。

  プロジェクトルートで:
    python scripts/check_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_server.chunk_store import ChunkStore  # noqa: E402
from bot_server.config import get_settings  # noqa: E402


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def _ng(msg: str) -> None:
    print(f"  [NG] {msg}")


def main() -> int:
    print("初期設定チェック（推奨構成: GAS 中継）\n")

    env_path = ROOT / ".env"
    if not env_path.is_file():
        _ng(".env がありません → python scripts/init_env.py")
        return 1
    _ok(f"{env_path.name} あり")

    get_settings.cache_clear()
    s = get_settings()

    exit_code = 0

    if not (s.internal_webhook_secret or "").strip():
        _ng("INTERNAL_WEBHOOK_SECRET が空（GAS から /internal/suggest-replies が使えません）")
        exit_code = 1
    else:
        _ok("INTERNAL_WEBHOOK_SECRET 設定済み（GAS のスクリプトプロパティと同じ値にしてください）")

    if not s.allow_direct_line_webhook:
        _ok("ALLOW_DIRECT_LINE_WEBHOOK=false（GAS のみ受け口・推奨）")
    else:
        _warn("ALLOW_DIRECT_LINE_WEBHOOK=true（/direct webhook も有効。GAS のみにするなら .env で false）")

    if not s.line_channel_secret and not s.line_channel_access_token:
        _ok("サーバ側に LINE_CHANNEL_* なし（GAS にだけ置く構成で問題ありません）")
    else:
        _warn("サーバに LINE_CHANNEL_* あり（直接 /webhook/line 用。GAS のみなら空でよい）")

    if s.gemini_api_key:
        _ok(f"GEMINI_API_KEY 設定済み（モデル: {s.gemini_model}）")
    else:
        _warn("GEMINI_API_KEY なし")

    if s.openai_api_key:
        _ok("OPENAI_API_KEY 設定済み（Gemini 未設定時のみ使用）")
    elif s.gemini_api_key:
        _ok("OPENAI 未使用（Gemini のみ）")
    else:
        _warn("OPENAI_API_KEY なし")

    if not s.gemini_api_key and not s.openai_api_key:
        _warn("LLM キーが両方空です（定型フォールバックのみ。本番は GEMINI_API_KEY 推奨）")

    rag_path = s.rag_chunks_path
    if not rag_path.is_file():
        _warn(f"RAG ファイルなし: {rag_path} → python scripts/build_rag_chunks.py")
    else:
        store = ChunkStore.load_jsonl(rag_path)
        if store.is_ready():
            _ok(f"RAG 読み込み可: {rag_path}")
        else:
            _warn(f"RAG ファイルはあるがチャンク0件: {rag_path}")

    print("\n--- 次のステップ ---")
    print("1) python run_server.py（別ターミナルでトンネル等で HTTPS 公開）")
    print("2) GET https://（公開URL）/health で rag_ready / internal_api_enabled を確認")
    print("3) GAS: SETUP.md のスクリプトプロパティを登録し、Webhook URL を LINE に設定")
    print("詳細: SETUP.md")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
