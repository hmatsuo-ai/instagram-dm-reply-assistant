"""
初期設定チェック（標準: LINE 直接 Webhook /webhook/line。GAS 中継も判定）。

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
    print("初期設定チェック\n")

    env_path = ROOT / ".env"
    if not env_path.is_file():
        _ng(".env がありません → python scripts/init_env.py")
        return 1
    _ok(f"{env_path.name} あり")

    get_settings.cache_clear()
    s = get_settings()

    exit_code = 0

    if s.allow_direct_line_webhook:
        _ok("ALLOW_DIRECT_LINE_WEBHOOK=true（LINE → /webhook/line）")
        if not (s.line_channel_secret or "").strip():
            _ng("LINE_CHANNEL_SECRET が空（直接 Webhook では必須）")
            exit_code = 1
        else:
            _ok("LINE_CHANNEL_SECRET 設定済み")
        if not (s.line_channel_access_token or "").strip():
            _ng("LINE_CHANNEL_ACCESS_TOKEN が空（直接 Webhook では必須）")
            exit_code = 1
        else:
            _ok("LINE_CHANNEL_ACCESS_TOKEN 設定済み")
    else:
        _ok("ALLOW_DIRECT_LINE_WEBHOOK=false（/webhook/line 無効）")
        if not (s.internal_webhook_secret or "").strip():
            _ng("INTERNAL_WEBHOOK_SECRET が空（GAS 等から /internal/suggest-replies を使うなら必須）")
            exit_code = 1
        else:
            _ok("INTERNAL_WEBHOOK_SECRET 設定済み（/internal/suggest-replies）")
        if s.line_channel_secret or s.line_channel_access_token:
            _warn("サーバに LINE_CHANNEL_* あり（GAS 中継のみなら通常は空）")

    if (s.internal_webhook_secret or "").strip():
        _ok("INTERNAL_WEBHOOK_SECRET あり（/internal/suggest-replies も利用可）")
    elif s.allow_direct_line_webhook:
        _warn("INTERNAL_WEBHOOK_SECRET なし（/internal/suggest-replies は無効で問題なし）")

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
        _warn("LLM キーが両方空（定型フォールバックのみ。本番は GEMINI_API_KEY 推奨）")

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
    print("本番 URL を決め、LINE Developers の Webhook を")
    print("  https://（公開ホスト）/webhook/line")
    print("に設定 → Verify。GET .../health で line_secret_configured を確認。")
    print("詳細: SETUP.md / VERCEL_DEPLOY.md")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
