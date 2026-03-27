"""
メッセージ履歴から「相手（候補者）からの発言が一度もない」スレッドを除外して整理する。

判定: messages 内にいずれかの要素で role=candidate（sender_name が business パターンに一致しない）
      となるものが 1 件もなければ「一方的（こちらのみ）」とみなす。

使い方:
  python scripts/prune_one_sided_threads.py --dry-run    # 件数のみ
  python scripts/prune_one_sided_threads.py --execute  # アーカイブへ移動

移動先: メッセージ履歴/messages/inbox_archived_one_sided/（フォルダ・直下jsonを構造維持で移動）
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from typing import Any

# build_rag_chunks と同じ判定ロジック（重複許容）
def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _repair_meta_export_mojibake(s: str) -> str:
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
    sn = _repair_meta_export_mojibake((sender_name or "").strip())
    if _is_business_sender(sn, patterns):
        return "business"
    if sn:
        return "candidate"
    return "unknown"


def _merge_messages_from_thread_dir(thread_dir: str) -> dict[str, Any] | None:
    files = sorted(
        glob.glob(os.path.join(thread_dir, "message_*.json")),
        key=lambda p: int(
            os.path.basename(p).replace("message_", "").replace(".json", "")
        ),
    )
    if not files:
        return None
    merged: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    for fp in files:
        try:
            data = _load_json(fp)
        except (json.JSONDecodeError, OSError):
            continue
        if not meta:
            meta = {
                k: data[k]
                for k in ("participants", "title", "thread_path", "is_still_participant")
                if k in data
            }
        merged.extend(data.get("messages") or [])
    if not merged:
        return None
    out = dict(meta)
    out["messages"] = merged
    return out


def _load_single_conversation_file(path: str) -> dict[str, Any] | None:
    try:
        data = _load_json(path)
    except (json.JSONDecodeError, OSError):
        return None
    if not (data.get("messages") or []):
        return None
    return data


def _has_candidate_message(data: dict[str, Any], patterns: list[str]) -> bool:
    for m in data.get("messages") or []:
        if _role(m.get("sender_name") or "", patterns) == "candidate":
            return True
    return False


def _paths_for_thread(
    inbox_root: str, kind: str, name: str
) -> tuple[str, str]:
    """(元パス, アーカイブ先パス)"""
    archive_root = os.path.join(
        os.path.dirname(inbox_root), "inbox_archived_one_sided"
    )
    if kind == "dir":
        src = os.path.join(inbox_root, name)
        dst = os.path.join(archive_root, "folders", name)
    else:
        src = os.path.join(inbox_root, name)
        dst = os.path.join(archive_root, "root_json", name)
    return src, dst


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_inbox = os.path.join(root, "メッセージ履歴", "messages", "inbox")
    default_config = os.path.join(root, "config", "rag_business_patterns.json")

    ap = argparse.ArgumentParser(description="一方的スレッドをアーカイブへ移動")
    ap.add_argument("--inbox", default=default_inbox)
    ap.add_argument("--config", default=default_config)
    ap.add_argument(
        "--execute",
        action="store_true",
        help="指定しない場合は dry-run（移動しない）",
    )
    args = ap.parse_args()

    inbox_root = args.inbox
    if not os.path.isdir(inbox_root):
        print(f"[error] inbox がありません: {inbox_root}", file=sys.stderr)
        sys.exit(1)

    patterns = _load_business_patterns(args.config)

    # サブフォルダ
    subdirs = sorted(
        d for d in glob.glob(os.path.join(inbox_root, "*")) if os.path.isdir(d)
    )
    # 直下 json
    root_json = sorted(
        f for f in glob.glob(os.path.join(inbox_root, "*.json")) if os.path.isfile(f)
    )

    to_move_dirs: list[str] = []
    to_move_files: list[str] = []

    for thread_dir in subdirs:
        merged = _merge_messages_from_thread_dir(thread_dir)
        if not merged:
            continue
        if not _has_candidate_message(merged, patterns):
            to_move_dirs.append(thread_dir)

    for fp in root_json:
        data = _load_single_conversation_file(fp)
        if not data:
            continue
        if not _has_candidate_message(data, patterns):
            to_move_files.append(fp)

    archive_root = os.path.join(
        os.path.dirname(inbox_root), "inbox_archived_one_sided"
    )
    summary = {
        "inbox": inbox_root,
        "one_sided_folders": len(to_move_dirs),
        "one_sided_root_json": len(to_move_files),
        "archived_to": archive_root,
        "dry_run": not args.execute,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.execute:
        print(
            "\n(dry-run) --execute でアーカイブへ移動します。",
            file=sys.stderr,
        )
        return

    os.makedirs(os.path.join(archive_root, "folders"), exist_ok=True)
    os.makedirs(os.path.join(archive_root, "root_json"), exist_ok=True)

    for thread_dir in to_move_dirs:
        name = os.path.basename(thread_dir)
        dst = os.path.join(archive_root, "folders", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(thread_dir, dst)

    for fp in to_move_files:
        name = os.path.basename(fp)
        dst = os.path.join(archive_root, "root_json", name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(dst):
                dst = os.path.join(archive_root, "root_json", f"{base}_{i}{ext}")
                i += 1
        shutil.move(fp, dst)

    print(f"[ok] archived to {archive_root}", file=sys.stderr)


if __name__ == "__main__":
    main()
