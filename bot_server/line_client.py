"""LINE replyMessage。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
MAX_TEXT_LEN = 4500


def _split_text(s: str, limit: int) -> list[str]:
    if len(s) <= limit:
        return [s]
    parts: list[str] = []
    while s:
        parts.append(s[:limit])
        s = s[limit:]
    return parts[:5]


async def reply_text(access_token: str, reply_token: str, text: str) -> bool:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    chunks = _split_text(text, MAX_TEXT_LEN)
    messages: list[dict[str, Any]] = [{"type": "text", "text": c} for c in chunks]
    payload = {"replyToken": reply_token, "messages": messages[:5]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(LINE_REPLY_URL, headers=headers, json=payload)
        if r.status_code != 200:
            logger.error("LINE reply failed: %s %s", r.status_code, r.text[:500])
            return False
    return True
