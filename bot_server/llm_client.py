"""返信案生成（OpenAI互換 API。キー未設定時はフォールバック）。"""

from __future__ import annotations

import logging
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


async def generate_replies(
    user_text: str,
    retrieved: list[tuple[Chunk, float]],
    *,
    api_key: str | None,
    base_url: str | None,
    model: str,
) -> tuple[list[str], list[str]]:
    """(replies のリスト, cited_chunk_ids) を返す。"""
    context = _format_context(retrieved)
    cited_ids = [c.chunk_id for c, _ in retrieved if c.chunk_id]

    if not api_key:
        logger.info("OPENAI_API_KEY 未設定: フォールバック応答")
        fallback = (
            "【参考案】\n\n"
            "【案1】\n"
            "お問い合わせありがとうございます。詳細は丁寧にご案内いたしますので、ご希望をもう少し教えてください。\n\n"
            "【案2】\n"
            "ご連絡ありがとうございます。ご不明点をまとめてお答えします。お時間のよいときにご返信ください。\n\n"
            "（LLM が未設定のため定型文です。.env に OPENAI_API_KEY を設定すると、RAG 参照つきで生成されます）\n\n"
            "--- RAG 参照抜粋 ---\n"
            + (context[:3500] if context else "（参照なし）")
        )
        return ([fallback], cited_ids)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        user_msg = f"担当者からの相談・転記:\n{user_text}\n\n類似履歴:\n{context}"
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
        return ([content], cited_ids)
    except Exception as e:
        logger.exception("LLM error: %s", e)
        err_reply = (
            "【エラー】返信案の生成に失敗しました。しばらくしてから再度お試しください。\n"
            f"（詳細はサーバログを確認: {e!s}）"
        )
        return ([err_reply], cited_ids)
