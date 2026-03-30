"""
Vercel 用エントリポイント。
公式ランタイムはリポジトリ直下の app / main / index 等から top-level `app` を探す。
"""

from bot_server.main import app

__all__ = ["app"]
