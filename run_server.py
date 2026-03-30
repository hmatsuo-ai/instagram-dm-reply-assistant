"""
自営サーバを起動（.env の HOST / PORT を使用）。

  pip install -r requirements-bot.txt
  python run_server.py
"""

from __future__ import annotations

import uvicorn

from bot_server.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(
        "bot_server.main:app",
        host=s.host,
        port=s.port,
        log_level=s.log_level,
    )
