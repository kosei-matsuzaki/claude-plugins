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
