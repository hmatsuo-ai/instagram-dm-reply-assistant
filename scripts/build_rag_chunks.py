"""
Instagram / Meta メッセージエクスポート JSON を走査し、RAG 用チャンクを JSONL に出力する。

使い方:
  python scripts/build_rag_chunks.py
  python scripts/build_rag_chunks.py --inbox "メッセージ履歴/messages/inbox" --out output/rag_chunks.jsonl

標準ライブラリのみ。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterator


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _repair_meta_export_mojibake(s: str) -> str:
    """
    Meta エクスポートで UTF-8 バイト列が \\u00xx として誤格納されている場合の修復。
    すでに正しい Unicode（日本語など）の文字列は latin-1 に載らないためそのまま返す。
    """
    if not s:
        return s
    try:
        s.encode("latin-1")
    except UnicodeEncodeError:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return s


def _load_business_patterns(config_path: str) -> list[str]:
    if not os.path.isfile(config_path):
        return ["ホスト求人"]
    data = _load_json(config_path)
    subs = data.get("business_substrings") or []
    return [str(s) for s in subs if s]


def _is_business_sender(sender_name: str, patterns: list[str]) -> bool:
    for p in patterns:
        if p in sender_name:
            return True
    return False


def _role(sender_name: str, patterns: list[str]) -> str:
    if _is_business_sender(sender_name, patterns):
        return "business"
    if sender_name.strip():
        return "candidate"
    return "unknown"


def _ts_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.isoformat()
    except (OSError, OverflowError, ValueError):
        return None


_PHONE_RE = re.compile(r"(0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})")


def _mask_pii(text: str, mask_phones: bool) -> str:
    if not mask_phones:
        return text
    return _PHONE_RE.sub("[電話番号]", text)


def _message_body(m: dict[str, Any]) -> str | None:
    content = m.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if m.get("photos"):
        return "[画像メッセージ]"
    if m.get("videos"):
        return "[動画メッセージ]"
    if m.get("audio_files"):
        return "[音声メッセージ]"
    if m.get("files"):
        return "[ファイル]"
    return None


def _stable_chunk_id(parts: list[str]) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return h


def _load_single_conversation_file(path: str) -> dict[str, Any] | None:
    """inbox 直下の 1 ファイル = 1 会話。"""
    try:
        data = _load_json(path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] skip {path}: {e}", file=sys.stderr)
        return None
    msgs = data.get("messages") or []
    if not msgs:
        return None
    data["_source_files"] = [path]
    return data


def _merge_messages_from_thread_dir(thread_dir: str) -> dict[str, Any] | None:
    """同一フォルダ内の message_1.json, message_2.json ... を結合。"""
    files = sorted(
        glob.glob(os.path.join(thread_dir, "message_*.json")),
        key=lambda p: int(os.path.basename(p).replace("message_", "").replace(".json", "")),
    )
    if not files:
        return None
    merged: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    for fp in files:
        try:
            data = _load_json(fp)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] skip {fp}: {e}", file=sys.stderr)
            continue
        if not meta:
            meta = {k: data[k] for k in ("participants", "title", "thread_path", "is_still_participant") if k in data}
        msgs = data.get("messages") or []
        merged.extend(msgs)
    if not merged:
        return None
    out = dict(meta)
    out["messages"] = merged
    out["_source_files"] = files
    return out


def _iter_conversation_sources(inbox_root: str) -> Iterator[tuple[dict[str, Any], str, str]]:
    """
    (merged_data, conversation_id, source_rel) を yield。
    source_rel はメタデータ用の相対パス表記。
    """
    # 1) サブフォルダ内 message_*.json
    subdirs = sorted(
        d for d in glob.glob(os.path.join(inbox_root, "*")) if os.path.isdir(d)
    )
    for thread_dir in subdirs:
        merged = _merge_messages_from_thread_dir(thread_dir)
        if not merged:
            continue
        thread_key = os.path.basename(thread_dir)
        rel = os.path.relpath(thread_dir, start=os.path.dirname(inbox_root))
        cid = (merged.get("thread_path") or rel).replace("\\", "/")
        source_rel = os.path.join("messages", "inbox", thread_key, "message_*.json").replace(
            "\\", "/"
        )
        yield merged, cid, source_rel

    # 2) inbox 直下の *.json（会話ファイル）
    for fp in sorted(glob.glob(os.path.join(inbox_root, "*.json"))):
        if not os.path.isfile(fp):
            continue
        merged = _load_single_conversation_file(fp)
        if not merged:
            continue
        base = os.path.basename(fp)
        cid = (merged.get("thread_path") or base.replace(".json", "")).replace("\\", "/")
        source_rel = os.path.join("messages", "inbox", base).replace("\\", "/")
        yield merged, cid, source_rel


def _format_line(role: str, label_biz: str, label_cand: str, body: str) -> str:
    if role == "business":
        prefix = f"[{label_biz}]"
    elif role == "candidate":
        prefix = f"[{label_cand}]"
    else:
        prefix = "[不明]"
    return f"{prefix} {body}"


def build_chunks_for_conversation(
    data: dict[str, Any],
    conversation_id: str,
    source_rel: str,
    patterns: list[str],
    window_size: int,
    window_stride: int,
    mask_phones: bool,
    label_business: str,
    label_candidate: str,
) -> list[dict[str, Any]]:
    raw_messages = data.get("messages") or []
    # 時系列（古い順）
    sorted_msgs = sorted(
        raw_messages,
        key=lambda m: (m.get("timestamp_ms") or 0, m.get("sender_name") or ""),
    )

    normalized: list[dict[str, Any]] = []
    for i, m in enumerate(sorted_msgs):
        sender = _repair_meta_export_mojibake((m.get("sender_name") or "").strip())
        body = _message_body(m)
        if body and not (body.startswith("[") and body.endswith("]")):
            body = _repair_meta_export_mojibake(body)
        if body is None:
            continue
        ts = m.get("timestamp_ms")
        r = _role(sender, patterns)
        normalized.append(
            {
                "index_in_thread": i,
                "sender_name": sender,
                "role": r,
                "sent_at": _ts_iso(ts) if isinstance(ts, (int, float)) else None,
                "text": _mask_pii(body, mask_phones),
            }
        )

    chunks: list[dict[str, Any]] = []

    # C-1: 単一メッセージ
    for idx, nm in enumerate(normalized):
        text = nm["text"]
        cid = _stable_chunk_id(
            [conversation_id, "single", str(idx), nm["sent_at"] or "", text[:200]]
        )
        chunks.append(
            {
                "chunk_id": cid,
                "chunk_type": "single_message",
                "conversation_id": conversation_id,
                "text": text,
                "metadata": {
                    "role": nm["role"],
                    "sent_at": nm["sent_at"],
                    "message_index": idx,
                    "source_file": source_rel,
                    "sender_name": nm["sender_name"],
                },
            }
        )

    # C-2: スライディングウィンドウ（文脈）
    if window_size < 2 or len(normalized) < 2:
        return chunks

    lines_for_window = [
        _format_line(nm["role"], label_business, label_candidate, nm["text"]) for nm in normalized
    ]

    w = min(window_size, len(lines_for_window))
    start = 0
    while start + w <= len(lines_for_window):
        window_lines = lines_for_window[start : start + w]
        block = "\n".join(window_lines)
        wid = _stable_chunk_id([conversation_id, "window", str(start), str(w), block[:300]])
        chunks.append(
            {
                "chunk_id": wid,
                "chunk_type": "window",
                "conversation_id": conversation_id,
                "text": block,
                "metadata": {
                    "window_start": start,
                    "window_len": w,
                    "source_file": source_rel,
                },
            }
        )
        start += window_stride
        if window_stride < 1:
            break

    return chunks


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_inbox = os.path.join(root, "メッセージ履歴", "messages", "inbox")
    default_out = os.path.join(root, "output", "rag_chunks.jsonl")
    default_config = os.path.join(root, "config", "rag_business_patterns.json")

    ap = argparse.ArgumentParser(description="メッセージ履歴から RAG 用 JSONL を生成")
    ap.add_argument("--inbox", default=default_inbox, help="inbox ルート")
    ap.add_argument("--out", default=default_out, help="出力 JSONL")
    ap.add_argument("--config", default=default_config, help="business 判定パターン JSON")
    ap.add_argument("--window-size", type=int, default=10, help="ウィンドウ最大行数（メッセージ数）")
    ap.add_argument("--window-stride", type=int, default=5, help="ウィンドウ開始位置のずらし幅")
    ap.add_argument("--no-mask-phones", action="store_true", help="電話番号マスクを無効化")
    ap.add_argument("--label-business", default="店舗", help="ウィンドウ内の business 表示ラベル")
    ap.add_argument("--label-candidate", default="候補者", help="ウィンドウ内の candidate 表示ラベル")
    ap.add_argument("--max-files", type=int, default=0, help="デバッグ用: 処理する会話数の上限（0=無制限）")
    ap.add_argument(
        "--append",
        action="store_true",
        help="既存の出力 JSONL に追記する（デフォルトは上書き）",
    )
    args = ap.parse_args()

    inbox_root = args.inbox
    if not os.path.isdir(inbox_root):
        print(f"[error] inbox が見つかりません: {inbox_root}", file=sys.stderr)
        sys.exit(1)

    patterns = _load_business_patterns(args.config)
    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    if not args.append and os.path.isfile(out_path):
        os.remove(out_path)

    total_chunks = 0
    total_conversations = 0
    errors = 0

    count = 0
    for merged, cid, source_rel in _iter_conversation_sources(inbox_root):
        try:
            chunks = build_chunks_for_conversation(
                merged,
                conversation_id=cid,
                source_rel=source_rel,
                patterns=patterns,
                window_size=args.window_size,
                window_stride=args.window_stride,
                mask_phones=not args.no_mask_phones,
                label_business=args.label_business,
                label_candidate=args.label_candidate,
            )
        except Exception as e:
            print(f"[warn] chunk build failed {cid}: {e}", file=sys.stderr)
            errors += 1
            continue

        with open(out_path, "a", encoding="utf-8") as out:
            for ch in chunks:
                rec = {
                    **ch,
                    "metadata": {
                        **ch.get("metadata", {}),
                        "schema_version": "1.0",
                    },
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total_chunks += 1

        total_conversations += 1
        count += 1
        if args.max_files and count >= args.max_files:
            break

    summary_path = os.path.join(os.path.dirname(out_path) or ".", "rag_build_summary.json")
    summary = {
        "inbox_root": inbox_root,
        "output_jsonl": out_path,
        "conversations_processed": total_conversations,
        "chunks_written": total_chunks,
        "errors": errors,
        "business_patterns": patterns,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
