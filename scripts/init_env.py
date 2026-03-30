"""
.env を .env.example からコピーする（GAS 不要の標準テンプレート）。

  プロジェクトルートで:
    python scripts/init_env.py
    python scripts/init_env.py --force   # 既存 .env を上書き（注意）
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"


def main() -> int:
    p = argparse.ArgumentParser(description="Create .env from .env.example")
    p.add_argument("--force", action="store_true", help="Overwrite existing .env")
    args = p.parse_args()

    if ENV_FILE.is_file() and not args.force:
        print(f"既に {ENV_FILE.name} があります。上書きは python scripts/init_env.py --force")
        return 0

    if not ENV_EXAMPLE.is_file():
        print(f"見つかりません: {ENV_EXAMPLE}", file=sys.stderr)
        return 1

    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print(f"作成しました: {ENV_FILE}")
    print("次: .env に LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN / GEMINI_API_KEY を入力")
    print("→ python scripts/check_setup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
