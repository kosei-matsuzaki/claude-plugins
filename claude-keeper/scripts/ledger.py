"""「いまは直さない」と決めたことを覚えておく台帳。

機械は候補しか出せない。3667 行のファイルを分けるべきか、その機能が要るか、
そのコメントが「なぜ」か言い換えかは、読まないと決まらない。読んで
「このままでよい」と決めたなら、**その判断を残す**。

残さないと同じ指摘が毎セッション出て、最後は notify.enabled: false にされる。
台帳はうるささを減らすためではなく、**黙らされるのを防ぐため**にある。

黙らせたものは消えない。check は必ず件数を出す (--show-judged で中身も出る)。
判断から 3 割伸びたら言い直し、**until を過ぎても言い直す** —
運営の判断は「直さない」ではなく「いまは直さない」であることが多い。
"""

import os
import re
import time

import policy as P

LEDGER = ".claude/judgments.yml"
# 統合前の置き場所。まだ残っていれば読む (init が移行を提案する)
LEGACY = (".code-keeper/judgments.yml", ".claude/crew-judgments.yml")
DEFAULT_REGROW = 0.3


def path_for(root):
    return os.path.join(root, LEDGER)


def _read_one(full):
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
    return [e for e in entries if isinstance(e, dict) and e.get("key")]


def load(root):
    """台帳を読む。統合前の置き場所も見る。壊れていても落とさない。"""
    out = _read_one(path_for(root))
    seen = {(e.get("path", ""), e["key"]) for e in out}
    for rel in LEGACY:
        for e in _read_one(os.path.join(root, rel)):
            if (e.get("path", ""), e["key"]) not in seen:
                out.append(e)
    return out


def legacy_files(root):
    return [r for r in LEGACY if os.path.isfile(os.path.join(root, r))]


def _expired(entry, today):
    until = entry.get("until")
    return isinstance(until, str) and bool(until.strip()) and until.strip() < today


def _grew(entry, record, regrow):
    """判断したときより大きくなったか。数で測れない指摘は、期限まで黙る。"""
    was, now = entry.get("at"), record.get("value")
    if not isinstance(was, (int, float)) or not isinstance(now, (int, float)) or was <= 0:
        return False
    return now > was * (1 + regrow)


def sift(records, entries, pol=None):
    """(出すもの, 黙らせたもの) に分ける。期限切れと、伸びたものは出す。"""
    regrow = P.opt(pol, "judgments.regrow", DEFAULT_REGROW)
    if not isinstance(regrow, (int, float)):
        regrow = DEFAULT_REGROW
    today = time.strftime("%Y-%m-%d")
    keep, hidden = [], []
    for record in records:
        match = None
        for entry in entries:
            if entry["key"] == record["key"] and entry.get("path", "") == record.get("path", ""):
                match = entry
                break
        if match is None:
            keep.append(record)
            continue
        why = None
        if _expired(match, today):
            why = "期限 %s を過ぎた" % match.get("until")
        elif _grew(match, record, regrow):
            why = "判断したとき (%s) から伸びた" % match.get("at")
        if why:
            record = dict(record)
            record["text"] += "  ← 前に「%s」と判断 (%s)。%s" % (
                match.get("decision") or "いまは直さない", match.get("date") or "日付なし", why)
            keep.append(record)
        else:
            hidden.append((record, match))
    return keep, hidden


# ------------------------------------------------------------------ 書き込み

def _quote(text):
    """体制ファイルと同じ狭い YAML で読めるようにする。改行と二重引用符は落とす。"""
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace('"', "'")
    return '"%s"' % text


def append(root, entry):
    """判断を 1 件足す。同じ (path, key) が既にあれば書き換える。"""
    full = path_for(root)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    entries = [
        e for e in load(root)
        if not (e.get("path", "") == entry.get("path", "") and e["key"] == entry["key"])
    ]
    entries.append(entry)
    lines = [
        "# 判断台帳。「いまは直さない」と決めたものを覚えておく。",
        "#",
        "# 消せばまた指摘される。判断が変わったら消すか、why を書き直す。",
        "# until を書くと、その日を過ぎたときにもう一度言う。運営の判断はたいてい期限付き。",
        "",
        "judgments:",
    ]
    for e in sorted(entries, key=lambda x: (x.get("path", ""), x["key"])):
        lines.append("  - key: %s" % _quote(e["key"]))
        if e.get("path"):
            lines.append("    path: %s" % e["path"])
        lines.append("    decision: %s" % _quote(e.get("decision") or "いまは直さない"))
        lines.append("    why: %s" % _quote(e.get("why")))
        if isinstance(e.get("at"), (int, float)):
            lines.append("    at: %d" % e["at"])
        if e.get("until"):
            lines.append("    until: %s" % e["until"])
        lines.append("    date: %s" % (e.get("date") or time.strftime("%Y-%m-%d")))
        if e.get("by"):
            lines.append("    by: %s" % _quote(e["by"]))
    with open(full, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return full
