"""
起動例（プロジェクトルートで）:
  pip install -r requirements-bot.txt
  copy .env.example .env
  （推奨）INTERNAL_WEBHOOK_SECRET と OPENAI_API_KEY のみ。LINE 秘密は GAS のスクリプトプロパティ（§3.5）
  python -m uvicorn bot_server.main:app --host 0.0.0.0 --port 8000

本番 HTTPS はリバースプロキシ・トンネル・または TLS 終端で対応（仕様書 §3.3）。
"""

from __future__ import annotations

import json
import logging
import secrets
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .chunk_store import ChunkStore
from .config import get_settings
from .line_client import reply_text
from .line_verify import verify_signature
from .suggest import build_reply_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

store: ChunkStore | None = None
_recent_message_ids: deque[str] = deque(maxlen=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    s = get_settings()
    store = ChunkStore.load_jsonl(s.rag_chunks_path)
    if not store.is_ready():
        logger.warning("RAG index empty or missing. Place output/rag_chunks.jsonl or run build_rag_chunks.py")
    if s.internal_webhook_secret:
        logger.info("POST /internal/suggest-replies 有効（Authorization: Bearer で保護）")
    if not s.line_channel_secret:
        if s.internal_webhook_secret:
            logger.info("GAS 中継想定: サーバに LINE_CHANNEL_SECRET なし（問題ありません）")
        else:
            logger.warning(
                "LINE_CHANNEL_SECRET 未設定: 直接 /webhook/line 利用時は署名検証しません"
            )
    if not s.internal_webhook_secret and not s.line_channel_secret:
        logger.warning("INTERNAL_WEBHOOK_SECRET も LINE_CHANNEL_SECRET も未設定です（本番前にいずれかを設定）")
    yield


app = FastAPI(title="LINE スカウト返信支援", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    s = get_settings()
    ready = store is not None and getattr(store, "is_ready", lambda: False)()
    return {
        "ok": True,
        "rag_ready": ready,
        "internal_api_enabled": bool(s.internal_webhook_secret),
        "direct_line_webhook_allowed": s.allow_direct_line_webhook,
        "line_secret_configured": bool(s.line_channel_secret),
        "line_token_configured": bool(s.line_channel_access_token),
        "llm_configured": bool(s.openai_api_key),
    }


class InternalSuggestBody(BaseModel):
    user_text: str = Field(..., min_length=1, max_length=8000)
    line_user_id: str | None = Field(default=None, max_length=64)


def _authorize_internal(request: Request) -> None:
    s = get_settings()
    if not s.internal_webhook_secret:
        raise HTTPException(status_code=404, detail="Internal API disabled")
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth[7:].strip()
    expected = s.internal_webhook_secret
    if len(token) != len(expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/internal/suggest-replies")
async def internal_suggest_replies(request: Request, body: InternalSuggestBody) -> dict[str, Any]:
    """GAS 等からのみ呼び出す。LINE の長期トークンはサーバに置かない構成用。"""
    _authorize_internal(request)
    s = get_settings()
    text, cited = await build_reply_text(body.user_text.strip(), store, s)
    if body.line_user_id:
        logger.info("suggest for line_user_id=%s (len=%d)", body.line_user_id, len(body.user_text))
    return {"text": text, "cited_chunk_ids": cited}


@app.post("/webhook/line")
async def line_webhook(request: Request) -> PlainTextResponse:
    s = get_settings()
    if not s.allow_direct_line_webhook:
        raise HTTPException(status_code=404, detail="Direct LINE webhook disabled")
    body = await request.body()
    sig = request.headers.get("X-Line-Signature")

    if s.line_channel_secret:
        if not verify_signature(s.line_channel_secret, body, sig):
            logger.warning("invalid LINE signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # LINE 接続確認はボディに events がないことがある
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = data.get("events") or []
    for ev in events:
        await _handle_event(ev, s)

    return PlainTextResponse("OK", status_code=200)


async def _handle_event(ev: dict[str, Any], s) -> None:
    etype = ev.get("type")
    if etype != "message":
        return
    msg = ev.get("message") or {}
    if msg.get("type") != "text":
        return
    mid = msg.get("id")
    if mid and mid in _recent_message_ids:
        return
    if mid:
        _recent_message_ids.append(str(mid))

    src = ev.get("source") or {}
    uid = src.get("userId")
    allowed = s.allowed_user_ids_set()
    if allowed is not None and uid not in allowed:
        logger.info("blocked user %s", uid)
        return

    reply_token = ev.get("replyToken")
    user_text = (msg.get("text") or "").strip()
    if not reply_token or not user_text:
        return

    if not s.line_channel_access_token:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN 未設定")
        return

    out, _cited = await build_reply_text(user_text, store, s)

    ok = await reply_text(s.line_channel_access_token, reply_token, out)
    if not ok:
        logger.error("reply failed for user=%s", uid)
