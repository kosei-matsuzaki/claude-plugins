"""Claude が下した判断を覚えておく台帳。

機械は「候補」しか出せない。3667 行のファイルが分けるべきなのか、
そのコメントが「なぜ」なのか言い換えなのかは、読まないと決まらない。
読んで「これはこのままでよい」と決めたなら、**その判断を残す**。

残さないと、同じ誤検出が毎セッション出て、最後は notify.enabled: false にされる。
台帳はうるささを減らすためではなく、**プラグインが黙らされるのを防ぐため**にある。

黙らせたものは消えない。check は必ず件数を出す (--show-judged で中身も出る)。
判断したときより 3 割伸びたら、判断を無視してもう一度言う
(「分けなくてよい」は、その大きさでの判断であって、永久の免罪符ではない)。
"""

import os
import re
import time

import policy as P

LEDGER = ".code-keeper/judgments.yml"
DEFAULT_REGROW = 0.3


def path_for(root):
    return os.path.join(root, LEDGER)


def load(root):
    """台帳を読む。無ければ空。壊れていても落とさない(黙って空として扱う)。"""
    full = path_for(root)
    if not os.path.isfile(full):
        return []
    try:
        with open(full, encoding="utf-8") as fh:
            data = P.parse_yaml(fh.read())
    except Exception:
        return []
    entries = data.get("judgments") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("path") and e.get("key")]


def _regrow(pol):
    val = P.opt(pol, "judgments.regrow", DEFAULT_REGROW)
    return val if isinstance(val, (int, float)) else DEFAULT_REGROW


def _grew(entry, record, regrow):
    """判断したときより大きくなったか。数で測れない指摘は、いつまでも黙る。"""
    was, now = entry.get("at"), record.get("value")
    if not isinstance(was, (int, float)) or not isinstance(now, (int, float)) or was <= 0:
        return False
    return now > was * (1 + regrow)


def sift(records, entries, pol):
    """(出すもの, 黙らせたもの) に分ける。伸びたものは黙らせずに出す。"""
    regrow = _regrow(pol)
    keep, hidden = [], []
    for record in records:
        match = None
        for entry in entries:
            if entry["path"] == record["path"] and entry["key"] == record["key"]:
                match = entry
                break
        if match is None:
            keep.append(record)
        elif _grew(match, record, regrow):
            record = dict(record)
            record["text"] += ("  ← 前に「%s」と判断 (%s、%s のとき)。そこから伸びた"
                               % (match.get("decision") or "このままでよい",
                                  match.get("date") or "日付なし", match.get("at")))
            keep.append(record)
        else:
            hidden.append((record, match))
    return keep, hidden


# ------------------------------------------------------------------ 書き込み

def _quote(text):
    """規約と同じ狭い YAML で読めるようにする。改行と二重引用符は落とす。"""
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace('"', "'")
    return '"%s"' % text


def append(root, entry):
    """判断を 1 件足す。同じ (path, key) が既にあれば書き換える。"""
    full = path_for(root)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    entries = [e for e in load(root)
               if not (e["path"] == entry["path"] and e["key"] == entry["key"])]
    entries.append(entry)
    lines = [
        "# code-keeper の判断台帳。Claude が「このままでよい」と決めたものを覚えておく。",
        "#",
        "# 消せばまた指摘される。判断が変わったら消すか、why を書き直す。",
        "# at はそのときの大きさ。ここから 3 割伸びたら、判断を無視してもう一度言う。",
        "",
        "judgments:",
    ]
    for e in sorted(entries, key=lambda x: (x["path"], x["key"])):
        lines.append("  - path: %s" % e["path"])
        lines.append("    key: %s" % _quote(e["key"]))
        lines.append("    decision: %s" % _quote(e.get("decision") or "このままでよい"))
        lines.append("    why: %s" % _quote(e.get("why")))
        if isinstance(e.get("at"), (int, float)):
            lines.append("    at: %d" % e["at"])
        lines.append("    date: %s" % (e.get("date") or time.strftime("%Y-%m-%d")))
        if e.get("by"):
            lines.append("    by: %s" % _quote(e["by"]))
    with open(full, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return full
