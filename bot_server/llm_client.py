"""返信案生成（Gemini 優先、次点で OpenAI 互換 API。いずれも未設定ならフォールバック）。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .chunk_store import Chunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたはナイトワーク求人のスカウト担当者向けアシスタントです。
入力には「候補者からの文面」や「状況」が含まれます。

以下のルールを厳守してください。
- 出力は【参考案】として、スカウト担当者がInstagram等にコピペするための返信文案（日本語）。
- 風営法等に抵触しうる断定的・誇大な表現は避ける。
- 過去の類似やり取り（参照チャンク）のトーンを参考にするが、個人名や特定できる情報は出さない。
- 返信案は **最大3つ**、それぞれ「【案1】」「【案2】」「【案3】」で始める（2つ以下でもよい）。
- 各案の後に改行を1行入れる。
"""


def _format_context(chunks: list[tuple[Chunk, float]]) -> str:
    lines = []
    for i, (ch, score) in enumerate(chunks, 1):
        lines.append(f"--- 参照{i} (score={score:.3f}, id={ch.chunk_id}) ---\n{ch.text}\n")
    return "\n".join(lines)


def _normalize_gemini_model(model: str) -> str:
    m = (model or "").strip()
    if m.startswith("models/"):
        return m[len("models/") :]
    return m or "gemini-2.0-flash"


def _gemini_extract_text(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else None
        raise ValueError(msg or "no candidates in Gemini response")
    content = (cands[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("text"):
            texts.append(str(p["text"]))
    return "".join(texts).strip()


async def _generate_gemini(
    user_msg: str,
    *,
    api_key: str,
    model: str,
) -> str:
    m = _normalize_gemini_model(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_msg}],
            }
        ],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 1200,
        },
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        r = await client.post(url, params={"key": api_key}, json=payload)
        r.raise_for_status()
        data = r.json()
    text = _gemini_extract_text(data)
    if not text:
        raise ValueError("empty Gemini completion")
    return text


async def _generate_openai(
    user_msg: str,
    *,
    api_key: str,
    base_url: str | None,
    model: str,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=1200,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("empty completion")
    return content


async def generate_replies(
    user_text: str,
    retrieved: list[tuple[Chunk, float]],
    *,
    gemini_api_key: str | None,
    gemini_model: str,
    openai_api_key: str | None,
    openai_base_url: str | None,
    openai_model: str,
) -> tuple[list[str], list[str]]:
    """(replies のリスト, cited_chunk_ids) を返す。"""
    context = _format_context(retrieved)
    cited_ids = [c.chunk_id for c, _ in retrieved if c.chunk_id]
    user_msg = f"担当者からの相談・転記:\n{user_text}\n\n類似履歴:\n{context}"

    if not (gemini_api_key or "").strip() and not (openai_api_key or "").strip():
        logger.info("GEMINI_API_KEY / OPENAI_API_KEY とも未設定: フォールバック応答")
        fallback = (
            "【参考案】\n\n"
            "【案1】\n"
            "お問い合わせありがとうございます。詳細は丁寧にご案内いたしますので、ご希望をもう少し教えてください。\n\n"
            "【案2】\n"
            "ご連絡ありがとうございます。ご不明点をまとめてお答えします。お時間のよいときにご返信ください。\n\n"
            "（LLM 未設定のため定型文です。.env に GEMINI_API_KEY または OPENAI_API_KEY を設定してください）\n\n"
            "--- RAG 参照抜粋 ---\n"
            + (context[:3500] if context else "（参照なし）")
        )
        return ([fallback], cited_ids)

    try:
        if (gemini_api_key or "").strip():
            content = await _generate_gemini(
                user_msg, api_key=gemini_api_key.strip(), model=gemini_model
            )
        else:
            content = await _generate_openai(
                user_msg,
                api_key=openai_api_key or "",
                base_url=openai_base_url or None,
                model=openai_model,
            )
        return ([content], cited_ids)
    except Exception as e:
        logger.exception("LLM error: %s", e)
        err_reply = (
            "【エラー】返信案の生成に失敗しました。しばらくしてから再度お試しください。\n"
            f"（詳細はサーバログを確認: {e!s}）"
        )
        return ([err_reply], cited_ids)
