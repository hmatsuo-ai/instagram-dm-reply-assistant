"""
.env を .env.example から生成し、INTERNAL_WEBHOOK_SECRET を自動採番する。

  プロジェクトルートで:
    python scripts/init_env.py
    python scripts/init_env.py --force   # 既存 .env を上書き（注意）
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"


def main() -> int:
    p = argparse.ArgumentParser(description="Create .env from .env.example with a random internal secret.")
    p.add_argument("--force", action="store_true", help="Overwrite existing .env")
    args = p.parse_args()

    if ENV_FILE.is_file() and not args.force:
        print(f"既に {ENV_FILE.name} があります。上書きは python scripts/init_env.py --force")
        return 0

    if not ENV_EXAMPLE.is_file():
        print(f"見つかりません: {ENV_EXAMPLE}", file=sys.stderr)
        return 1

    raw = ENV_EXAMPLE.read_text(encoding="utf-8")
    lines_out: list[str] = []
    filled_secret = False
    for line in raw.splitlines():
        if line.startswith("INTERNAL_WEBHOOK_SECRET="):
            rest = line[len("INTERNAL_WEBHOOK_SECRET=") :].strip()
            if not rest:
                line = f"INTERNAL_WEBHOOK_SECRET={secrets.token_hex(32)}"
                filled_secret = True
        lines_out.append(line)

    body = "\n".join(lines_out) + "\n"
    ENV_FILE.write_text(body, encoding="utf-8")
    print(f"作成しました: {ENV_FILE}")
    if filled_secret:
        print("INTERNAL_WEBHOOK_SECRET を自動生成しました。")
    print("次: .env に GEMINI_API_KEY= を追記（推奨）→ python scripts/check_setup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
