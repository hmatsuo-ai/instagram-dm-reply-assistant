"""会話JSONから「体験・来店合意っぽい」候補者発言があるスレッド数を数える（ヒューリスティック）。"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "メッセージ履歴",
    "messages",
)


def repair(s: str) -> str:
    if not s:
        return ""
    try:
        s.encode("latin-1")
    except UnicodeEncodeError:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return s


STRICT = [
    re.compile(r"体験.{0,60}(お願い|行く|行っ|伺い|参加|します|きます|したい)", re.I),
    re.compile(r"(来店|お店|店舗).{0,40}(伺い|行き|いき|お邪魔|します)", re.I),
    re.compile(r"(当日|日程|時間).{0,35}(大丈夫|了解|OKで|お願い|決まり|調整|伺い)", re.I),
    re.compile(r"(ぜひ|是非).{0,25}(体験|お願い)", re.I),
    re.compile(r"(面接|説明).{0,25}(受け|お願い|伺い|行き)", re.I),
    re.compile(r"(アルバイト|バイト).{0,30}(やり|始め|します|お願い)", re.I),
    re.compile(r"入店.{0,20}(お願い|希望|考え)", re.I),
]


def msg_body(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str) and c.strip():
        return repair(c.strip())
    return ""


def is_candidate(sender: str | None) -> bool:
    s = repair((sender or "").strip())
    return bool(s and "ホスト求人" not in s)


def thread_has_strict_success(data: dict) -> tuple[bool, str | None]:
    cid = data.get("thread_path")
    for m in data.get("messages") or []:
        if not is_candidate(m.get("sender_name")):
            continue
        text = msg_body(m)
        if not text:
            continue
        for rx in STRICT:
            if rx.search(text):
                return True, cid
    return False, cid


def main() -> None:
    utf8 = sys.stdout.encoding and sys.stdout.encoding.lower() in ("utf-8", "utf8")
    out = sys.stdout if utf8 else None

    def pr(*a: object) -> None:
        line = " ".join(str(x) for x in a)
        if utf8:
            print(line)
        else:
            print(line.encode("utf-8", errors="backslashreplace").decode("ascii", errors="replace"))

    strict_ids: set[str] = set()
    for fp in glob.glob(os.path.join(BASE, "**", "*.json"), recursive=True):
        if not os.path.isfile(fp):
            continue
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ok, cid = thread_has_strict_success(data)
        if ok and cid:
            strict_ids.add(cid.replace("\\", "/"))

    pr("strict_success_like_thread_count:", len(strict_ids))
    for cid in sorted(strict_ids):
        pr(" -", cid)


if __name__ == "__main__":
    main()
