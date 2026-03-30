"""
LINE の長期トークン・チャネルシークレットを環境変数から読み、疎通確認する。

  LINE_CHANNEL_ACCESS_TOKEN=... LINE_CHANNEL_SECRET=... python scripts/verify_line_env.py

リポジトリに秘密を書かないこと。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys

import httpx


def main() -> int:
    token = (os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
    secret = (os.environ.get("LINE_CHANNEL_SECRET") or "").strip()

    if not token:
        print("NG: LINE_CHANNEL_ACCESS_TOKEN が空です")
        return 1

    try:
        r = httpx.get(
            "https://api.line.me/v2/bot/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
    except Exception as e:
        print("NG: リクエスト失敗:", e)
        return 2

    print(f"GET https://api.line.me/v2/bot/info → {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print("OK ボット情報:")
        print(f"  userId: {data.get('userId')}")
        print(f"  displayName: {data.get('displayName')}")
    else:
        print("NG 応答本文（先頭）:", r.text[:400])
        return 2

    if not secret:
        print("（LINE_CHANNEL_SECRET 未設定のため署名テストはスキップ）")
        return 0

    body = b'{"events":[]}'
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()
    ok = expected == base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()
    print(f"チャネルシークレット HMAC 自己整合: {'OK' if ok else 'NG'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
