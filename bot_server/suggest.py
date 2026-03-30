"""返信テキスト組み立て（Webhook 直／内部 API 共用）。"""

from __future__ import annotations

from .chunk_store import ChunkStore
from .config import Settings
from .llm_client import generate_replies


async def build_reply_text(
    user_text: str,
    store: ChunkStore | None,
    s: Settings,
) -> tuple[str, list[str]]:
    top_k = s.rag_top_k
    retrieved: list = []
    if store and store.is_ready():
        retrieved = store.search(user_text, top_k)

    replies, cited = await generate_replies(
        user_text,
        retrieved,
        gemini_api_key=s.gemini_api_key,
        gemini_model=s.gemini_model,
        openai_api_key=s.openai_api_key,
        openai_base_url=s.openai_base_url,
        openai_model=s.openai_model,
    )
    out = "\n\n".join(replies)
    if cited:
        out += "\n\n---\n参照 chunk_id: " + ", ".join(cited[:12])
        if len(cited) > 12:
            out += " ..."
    return out, cited
