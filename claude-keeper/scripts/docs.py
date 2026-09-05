"""docs を数える。行数・索引・置き場所・記録・実装との対応。

コードと同じで、数えられることだけをやる。「その記述が正しいか」は
読まないと決まらないので、役 (docs-auditor) と /docs が引き受ける。

指摘は report.py と同じ形で返す。台帳が 1 つで済むように、鍵の付け方もそろえる。
"""

import json
import os
import re

import policy as P
from report import rec

SKIP_DIRS = {
    ".git", "node_modules", "build", ".dart_tool", "Pods", "vendor",
    ".venv", "venv", "__pycache__", ".next", "dist", ".gradle", "target",
}
DOC_EXTS = (".md", ".ipynb")


def all_docs(root, exts=DOC_EXTS):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.lower().endswith(tuple(exts)):
                rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
                if not rel.startswith(".."):
                    found.append(rel)
    return sorted(found)


def doc_size(root, relpath):
    """(大きさ, 単位)。md は行数、notebook はセル数で数える。"""
    path = os.path.join(root, relpath)
    if relpath.lower().endswith(".ipynb"):
        try:
            with open(path, encoding="utf-8") as fh:
                return len(json.load(fh).get("cells") or []), "セル"
        except Exception:
            return 0, "セル"
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh), "行"
    except Exception:
        return 0, "行"


def archive_dir(pol):
    d = P.opt(pol, "archive.dir")
    if not isinstance(d, str) or not d:
        return None
    return d if d.endswith("/") else d + "/"


def in_archive(pol, relpath):
    d = archive_dir(pol)
    return bool(d) and P.matches_any(relpath, [d])


def cap_for(pol, relpath):
    """その文書の行数上限。archive の中は rotate.max_lines が優先。"""
    if in_archive(pol, relpath) and relpath.lower().endswith(".md"):
        cap = P.opt(pol, "archive.rotate.max_lines")
        if isinstance(cap, int):
            return cap, True
    cap = P.doc_limit(pol, relpath)
    return (cap if isinstance(cap, int) else None), False


def index_targets(root, index_rel):
    """索引が指している先。markdown リンクと、素の path 記述の両方を拾う。"""
    if not index_rel:
        return None
    path = os.path.join(root, index_rel)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except Exception:
        return None
    base = os.path.dirname(index_rel)
    targets = set()
    for href in re.findall(r"\]\(([^)\s]+)\)", text):
        href = href.split("#")[0]
        if not href or href.startswith(("http://", "https://", "mailto:")):
            continue
        targets.add(os.path.normpath(os.path.join(base, href)).replace(os.sep, "/"))
    return targets, text


# --------------------------------------------------------------- 見出しを読む

FENCE = re.compile(r"^\s*(?:```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# どの文書にも出る見出し。重なっても「散っている」印にはならない。
GENERIC_HEADINGS = {
    "概要", "はじめに", "目次", "前提", "使い方", "つかいかた", "構成", "参考",
    "注意", "メモ", "備考", "まとめ", "ライセンス", "テスト", "開発", "動かす",
    "背景", "目的", "その他", "索引", "手順", "todo", "faq",
    "overview", "usage", "install", "setup", "getting started", "notes",
    "reference", "references", "license", "testing", "development",
    "background", "goals", "index",
}


def norm_heading(text):
    """飾りと番号を落として突き合わせる形にする。"""
    text = re.sub(r"[`*_:：]", "", text)
    text = re.sub(r"\s*[（(][^（()）]*[)）]\s*$", "", text)
    text = re.sub(r"^[\s\d０-９.．、)）-]+", "", text)
    return " ".join(text.split()).lower()


def headings(root, relpath, max_level=3):
    """(段, 見出し, 行番号) の一覧。コードブロックの中は見出しとして数えない。"""
    if not relpath.lower().endswith(".md"):
        return []
    out, fenced = [], False
    try:
        with open(os.path.join(root, relpath), encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if FENCE.match(line):
                    fenced = not fenced
                    continue
                if fenced:
                    continue
                m = HEADING.match(line)
                if m and len(m.group(1)) <= max_level:
                    out.append((len(m.group(1)), m.group(2), n))
    except Exception:
        return []
    return out


# ------------------------------------------------------------------- findings

def size_findings(root, pol, docs):
    out = []
    for m in docs:
        cap, archived = cap_for(pol, m)
        if not isinstance(cap, int):
            continue
        n, unit = doc_size(root, m)
        if n <= cap:
            continue
        advice = "割りどき" if archived else "archive 送りか圧縮どき"
        out.append(rec(m, "doc_lines:" + m,
                       "%s が %d %s (上限 %d)。%s" % (m, n, unit, cap, advice),
                       "/docs", value=n))
    return out


def orphan_findings(root, pol, docs):
    """索引から辿れないもの / 索引が指しているのに存在しないもの。"""
    idx = P.opt(pol, "index")
    res = index_targets(root, idx)
    if not res:
        return [], []
    targets, text = res
    base = os.path.dirname(idx) + "/" if os.path.dirname(idx) else ""
    orphans = [
        rec(m, "orphan:" + m, "%s が索引 %s から辿れない" % (m, idx), "/docs")
        for m in docs
        if m != idx and m.startswith(base) and m not in targets
        and m not in text and os.path.basename(m) not in text
    ]
    missing = [
        rec(idx, "missing:" + t, "索引 %s が %s を指しているが、存在しない" % (idx, t), "/docs")
        for t in sorted(targets)
        if t.lower().endswith(DOC_EXTS) and not os.path.exists(os.path.join(root, t))
    ]
    return orphans, missing


def stray_findings(pol, docs):
    """規約にない置き場所の文書。"""
    layout = [d for d, _ in P.layout_paths(pol)]
    if not layout:
        return []
    scope = P.opt(pol, "guard.scope", ["docs/**"])
    return [
        rec(m, "stray:" + m, "%s は規約にない置き場所" % m, "/docs")
        for m in docs
        if P.matches_any(m, scope) and not P.matches_any(m, layout)
    ]


def layout_findings(root, pol):
    """規約が置き場所として挙げているのに、実在しないもの。

    **規約は現状の写しでなければ意味がない。**実在しない場所が載っていると、
    guard はそこへの書き込みを許し、watch はそこが未更新だと言い続ける。
    どちらも「あるはずのもの」を前提にした嘘の指摘になる。
    """
    out = []
    for path, _ in P.layout_paths(pol):
        if any(c in path for c in "*?{"):
            continue                      # 場所ではなく形の指定。実在を問わない
        full = os.path.join(root, path)
        if path.endswith("/"):
            ok = os.path.isdir(full.rstrip("/"))
        else:
            ok = os.path.exists(full)
        if not ok:
            out.append(rec(path, "layout:" + path,
                           "規約の docs.layout に %s があるが、実在しない" % path,
                           "/docs"))
    return out


def watch_findings(pol, changed):
    """触った実装に対して、対応する文書が動いていない。"""
    out = []
    for i, rule in enumerate(P.watch_rules(pol)):
        src = sorted(c for c in changed if P.matches_any(c, rule["source"]))
        if not src or any(P.matches_any(c, rule["docs"]) for c in changed):
            continue
        why = ("(%s)" % rule["why"]) if rule["why"] else ""
        head = " ".join(src[:2]) + ("" if len(src) <= 2 else " ほか %d 件" % (len(src) - 2))
        out.append(rec(rule["docs"][0] if rule["docs"] else "", "watch:%d" % i,
                       "%s を変更 %s → %s が未更新" % (head, why, " / ".join(rule["docs"])),
                       "/docs"))
    return out


def overlap_findings(root, pol, docs):
    """同じ見出しが複数の文書に出ている。仕様や設計が散っている印。

    **同じ話かどうかは読まないと決まらない。**機械は場所を並べるだけで、
    まとめるか分けるかは /docs と docs-auditor が決める。ここが無いと、
    行数も索引も置き場所も通ったまま、仕様が 3 つの文書に散った状態が
    「問題なし」として通る。
    """
    if not P.opt(pol, "overlap.enabled", True):
        return []
    scope = P.opt(pol, "overlap.scope", ["*.md", "docs/*.md"])
    ignore = {norm_heading(h) for h in P.opt(pol, "overlap.ignore", []) or []}
    least = P.opt(pol, "overlap.min_docs", 2)
    if not isinstance(least, int) or isinstance(least, bool) or least < 2:
        least = 2
    where = {}
    for m in docs:
        if in_archive(pol, m) or not P.matches_any(m, scope):
            continue
        for lvl, text, line in headings(root, m):
            if lvl < 2:
                continue          # 文書の題名。話題ではない
            key = norm_heading(text)
            if len(key) < 2 or key in GENERIC_HEADINGS or key in ignore:
                continue
            where.setdefault(key, {}).setdefault(m, line)
    out = []
    for key in sorted(where):
        places = where[key]
        if len(places) < least:
            continue
        at = " / ".join("%s:%d" % (m, places[m]) for m in sorted(places))
        out.append(rec(sorted(places)[0], "overlap:" + key,
                       "「%s」が %d か所にある (%s)" % (key, len(places), at),
                       "/docs", value=len(places)))
    return out


def section_findings(root, pol):
    """CLAUDE.md の節が伸びている。長い節は docs へ出す候補。

    CLAUDE.md は毎セッション全文が読まれるので、長さがそのまま費用になる。
    **全体の行数だけを見ていると、上限の内側で設計書を抱え込んだまま気づけない。**
    """
    relpath = P.opt(pol, "claude_md.path", "CLAUDE.md")
    cap = P.opt(pol, "claude_md.max_section_lines", 25)
    if not isinstance(relpath, str) or not relpath:
        return []
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        return []
    if not os.path.isfile(os.path.join(root, relpath)):
        return []
    heads = [(text, line) for lvl, text, line in headings(root, relpath, 2) if lvl == 2]
    if not heads:
        return []
    total, _ = doc_size(root, relpath)
    bounds = heads + [("", total + 1)]
    out = []
    for i, (text, line) in enumerate(heads):
        n = bounds[i + 1][1] - line
        if n <= cap:
            continue
        out.append(rec(relpath, "section:%s:%s" % (relpath, norm_heading(text)),
                       "%s の「%s」が %d 行 (上限 %d)。docs へ出して 1 行で指す候補"
                       % (relpath, text, n, cap),
                       "/docs", line=line, value=n))
    return out


# ------------------------------------------------------------- 二重管理を探す

# 実質のない行は突き合わせに使わない。短い行は偶然そろう。
MIN_LINE_CHARS = 12

_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_QUOTE = re.compile(r"^\s*>+\s*")
_HEAD = re.compile(r"^\s*#{1,6}\s+")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def norm_line(text):
    """飾りを落として字面だけにする。書き方が違っても同じ事実なら合うように。"""
    t = _QUOTE.sub("", text)
    t = _HEAD.sub("", t)
    t = _LIST.sub("", t)
    t = _LINK.sub(r"\1", t)
    t = re.sub(r"[`*_~]", "", t)
    return " ".join(t.split()).strip().lower()


def content_lines(root, relpath):
    """(行番号, 字面) の一覧。実質のない行は落とす。**コードブロックも入れる** —
    同じコマンドが CLAUDE.md と README.md に並ぶのは、いちばん多い二重管理。
    """
    if not relpath.lower().endswith(".md"):
        return []
    out = []
    try:
        with open(os.path.join(root, relpath), encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if FENCE.match(line):
                    continue
                t = norm_line(line)
                if len(t) >= MIN_LINE_CHARS:
                    out.append((n, t))
    except Exception:
        return []
    return out


def duplicate_findings(root, pol, docs):
    """同じ文が複数の文書に書かれている。二重管理は**片方が必ず古くなる。**

    見出しが違っていても字面がそろっていれば拾えるので、overlap (見出しの
    重なり) では見えないものを見る。逆に、言い回しを変えて写したものは
    ここでは出ない。それを見るのは役 (duplication-auditor)。
    """
    if not P.opt(pol, "duplication.enabled", True):
        return []
    scope = P.opt(pol, "duplication.scope", ["*.md", "docs/**"])
    ignore = P.opt(pol, "duplication.ignore", []) or []
    span = P.opt(pol, "duplication.min_lines", 3)
    chars = P.opt(pol, "duplication.min_chars", 80)
    if not isinstance(span, int) or isinstance(span, bool) or span < 1:
        span = 3
    if not isinstance(chars, int) or isinstance(chars, bool) or chars < 1:
        chars = 80

    files, lines = [], []
    for m in docs:
        if in_archive(pol, m) or not P.matches_any(m, scope) or P.matches_any(m, ignore):
            continue
        got = content_lines(root, m)
        if len(got) >= span:
            files.append(m)
            lines.append(got)

    # 同じかたまりが出てくる場所を集める。位置は「実質のある行」の番号で持つ。
    where = {}
    for fi, got in enumerate(lines):
        for k in range(len(got) - span + 1):
            win = [t for _, t in got[k:k + span]]
            if len(set(win)) < 2 and span > 1:
                continue                      # 同じ行の繰り返し。定型
            if sum(len(t) for t in win) < chars:
                continue
            where.setdefault("\n".join(win), []).append((fi, k))

    pairs = set()
    for occ in where.values():
        if len(occ) < 2 or len(occ) > 6:      # 6 か所以上に出るものは定型文
            continue
        for a in range(len(occ)):
            for b in range(a + 1, len(occ)):
                (f1, k1), (f2, k2) = occ[a], occ[b]
                if f1 == f2 and abs(k1 - k2) < span:
                    continue                  # 同じ場所の重なり
                pairs.add((f1, k1, f2, k2))

    out = []
    for (f1, k1, f2, k2) in sorted(pairs):
        if (f1, k1 - 1, f2, k2 - 1) in pairs:
            continue                          # かたまりの途中。頭だけを出す
        n = span
        while (f1, k1 + n - span + 1, f2, k2 + n - span + 1) in pairs:
            n += 1
        a, b = files[f1], files[f2]
        ra = "%s:%d-%d" % (a, lines[f1][k1][0], lines[f1][k1 + n - 1][0])
        rb = "%s:%d-%d" % (b, lines[f2][k2][0], lines[f2][k2 + n - 1][0])
        out.append((n, a, ra, rb, lines[f1][k1][1]))
    out.sort(key=lambda d: -d[0])

    seen, recs = set(), []
    for n, a, ra, rb, head in out:
        key = (ra.split(":")[0], rb.split(":")[0])
        if key in seen:
            continue                          # 同じ 2 文書からは 1 件だけ出す
        seen.add(key)
        recs.append(rec(a, "dup:%s|%s" % key,
                        "%s と %s に同じ %d 行 (「%s…」)" % (ra, rb, n, head[:24]),
                        "/docs", value=n))
    return recs
