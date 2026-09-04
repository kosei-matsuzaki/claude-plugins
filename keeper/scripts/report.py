"""数え上げた結果から「見立て」を作る。ここは入出力を持たない。

scan.py と clones.py が数え、report.py が規約と照らして候補にし、ck.py が見せる。

**ここが出すのは「見るべき場所」で、「直すべき場所」ではない。**
分けるべきか・まとめてよいかはコードを読まないと決まらない。決めるのは
Claude (コマンド側) で、決めた結果は ledger.py が覚える。

指摘 1 件 = record。kind / path / line / key / value / text / cmd を持つ。
key は台帳と突き合わせる鍵で、行がずれても変わらない形にしてある。
"""

import os

import clones as C
import policy as P
import scan as S

# 規約がまだ無いリポジトリでも check が動くように、控えめな既定値を持つ。
DEFAULTS = {
    "file_lines": 400, "function_lines": 60, "nesting": 4, "params": 5, "dir_files": 20,
}
DEF_COMMENTS = {"min_ratio": 0.02, "max_ratio": 0.4, "max_block": 20, "require_for_lines": 40}


def lim(pol, key, relpath):
    val = P.limit_for(pol, key, relpath)
    return val if isinstance(val, int) else DEFAULTS.get(key)


def comment_opt(pol, key):
    val = P.opt(pol, "comments." + key)
    return val if isinstance(val, (int, float)) else DEF_COMMENTS[key]


def collect(root, pol, files):
    data = {}
    for rel_path in files:
        info = S.analyze(root, rel_path)
        if info:
            data[rel_path] = info
    return data


def rec(path, key, text, cmd, **extra):
    """指摘 1 件。kind は key の頭から取る。line と value は extra で渡す。"""
    out = {"kind": key.split(":")[0], "path": path, "key": key, "text": text,
           "cmd": cmd, "line": 0, "value": None}
    out.update(extra)
    return out


def _at(path, line):
    return "%s:%d" % (path, line) if line else path


# -------------------------------------------------------------------- 長さ

def size_findings(pol, data, targets):
    """長さと入れ子。ファイル単位と関数単位の両方を見る。"""
    out = []
    for rel_path in targets:
        info = data.get(rel_path)
        if not info:
            continue
        cap = lim(pol, "file_lines", rel_path)
        if cap and info["total"] > cap:
            out.append(rec(rel_path, "file_lines",
                           "%s が %d 行 (上限 %d)" % (rel_path, info["total"], cap),
                           "split", value=info["total"]))
        caps = {k: lim(pol, k, rel_path) for k in ("function_lines", "nesting", "params")}
        for fn in info["funcs"]:
            name, at = fn["name"], _at(rel_path, fn["start"])
            if caps["function_lines"] and fn["lines"] > caps["function_lines"]:
                out.append(rec(rel_path, "function_lines:" + name,
                               "%s %s() が %d 行 (上限 %d)"
                               % (at, name, fn["lines"], caps["function_lines"]),
                               "split", line=fn["start"], value=fn["lines"]))
            elif caps["nesting"] and fn["depth"] > caps["nesting"]:
                out.append(rec(rel_path, "nesting:" + name,
                               "%s %s() の入れ子が %d 段 (上限 %d)"
                               % (at, name, fn["depth"], caps["nesting"]),
                               "split", line=fn["start"], value=fn["depth"]))
            elif caps["params"] and fn["params"] > caps["params"]:
                out.append(rec(rel_path, "params:" + name,
                               "%s %s() の引数が %d 個 (上限 %d)"
                               % (at, name, fn["params"], caps["params"]),
                               "split", line=fn["start"], value=fn["params"]))
    return out


# ---------------------------------------------------------------- コメント

def comment_findings(pol, data, targets):
    """量だけを見る。中身が「なぜ」か言い換えかは、ここでは決められない。"""
    lo, hi = comment_opt(pol, "min_ratio"), comment_opt(pol, "max_ratio")
    max_block, need = comment_opt(pol, "max_block"), comment_opt(pol, "require_for_lines")
    out = []
    for rel_path in targets:
        info = data.get(rel_path)
        if not info or info["code"] < 40:   # 短いファイルに比率を当てても意味がない
            continue
        ratio = info["comment"] / float(info["code"] or 1)
        for start, end, codeish in info["blocks"]:
            if codeish >= 3:
                out.append(rec(rel_path, "commented_out",
                               "%s:%d %d 行のコメントアウトされたコード (%d-%d 行)"
                               % (rel_path, start, end - start + 1, start, end),
                               "comment", line=start, value=end - start + 1))
            elif end - start + 1 > max_block:
                out.append(rec(rel_path, "long_comment",
                               "%s:%d %d 行続くコメント (上限 %d)"
                               % (rel_path, start, end - start + 1, max_block),
                               "comment", line=start, value=end - start + 1))
        if ratio < lo:
            out.append(rec(rel_path, "comment_thin",
                           "%s コメントが %.0f%% (下限 %.0f%%)。なぜが残っているか読む"
                           % (rel_path, ratio * 100, lo * 100), "comment", value=int(ratio * 100)))
        elif ratio > hi:
            out.append(rec(rel_path, "comment_thick",
                           "%s コメントが %.0f%% (上限 %.0f%%)。言い換えが混じっていないか読む"
                           % (rel_path, ratio * 100, hi * 100), "comment", value=int(ratio * 100)))
        for fn in info["funcs"]:
            if fn["lines"] < need:
                continue
            head = max(fn["start"] - 3, 1)
            near = any(s <= fn["start"] + 1 and e >= head for s, e, _ in info["blocks"])
            if not near:
                out.append(rec(rel_path, "undocumented:" + fn["name"],
                               "%s %s() は %d 行あるのに説明が無い"
                               % (_at(rel_path, fn["start"]), fn["name"], fn["lines"]),
                               "comment", line=fn["start"], value=fn["lines"]))
    return out


# ------------------------------------------------------------------ 層と構成

def layer_findings(pol, data, targets=None):
    layers = P.layers(pol)
    if not layers:
        return [], []
    edge_list, homeless = S.edges(None, data, layers)
    bad = [rec(src, "layer:" + dst, "%s → %s (%s)" % (src, dst, why), "relayout")
           for src, dst, why in S.violations(edge_list)]
    lost = [rec(p, "homeless", "%s がどの層にも属していない" % p, "relayout")
            for p in homeless]
    if targets is not None:
        keep = set(targets)
        bad = [b for b in bad if b["path"] in keep]
        lost = [l for l in lost if l["path"] in keep]
    return bad, lost


def dir_findings(pol, data):
    """1 つのディレクトリに入りすぎているもの。分け方を決めていない印。"""
    counts = {}
    for rel_path in data:
        key = os.path.dirname(rel_path) or "."
        counts[key] = counts.get(key, 0) + 1
    out = []
    for dirname, num in sorted(counts.items()):
        cap = lim(pol, "dir_files", dirname + "/x")
        if cap and num > cap:
            out.append(rec(dirname, "dir_files",
                           "%s/ に %d ファイル (上限 %d)" % (dirname, num, cap),
                           "relayout", value=num))
    return out


# -------------------------------------------------------------------- 重なり

def dup_findings(pol, data, targets=None):
    """行がそのまま重なっているもの。**形が違う重なりは similar_findings。**"""
    min_lines = P.opt(pol, "duplication.min_lines", 8)
    ignore = P.as_list(P.opt(pol, "duplication.ignore"))
    subset = {k: v for k, v in data.items() if not P.matches_any(k, ignore)}
    out = []
    for d in C.duplicates(subset, min_lines if isinstance(min_lines, int) else 8):
        a, b = sorted([d["a"], d["b"]])
        out.append(rec(a[0], "dup:" + b[0],
                       "%s:%d-%d  ≡  %s:%d-%d  (%d 行そのまま同じ)"
                       % (a[0], a[1], a[2], b[0], b[1], b[2], d["lines"]),
                       "unify", line=a[1], value=d["lines"], a=a, b=b))
    if targets is not None:
        keep = set(targets)
        out = [r for r in out if r["a"][0] in keep or r["b"][0] in keep]
    return out


def similar_findings(pol, data, targets=None):
    """形は似ているが、行はそろっていない関数のかたまり。

    FE のボタンのように、同じ骨組みで文言と色だけ違うものはここに出る。
    完全一致の検出では絶対に見つからない — そして、たいてい共通化できるのはこちら。

    **ただし似ていることと、まとめてよいことは別。** 決めるのは読んだ人。
    """
    ratio = P.opt(pol, "duplication.similar", 0.85)
    ratio = ratio if isinstance(ratio, (int, float)) else 0.85
    if not ratio:
        return []
    ignore = P.as_list(P.opt(pol, "duplication.ignore"))
    subset = {k: v for k, v in data.items() if not P.matches_any(k, ignore)}
    min_lines = P.opt(pol, "duplication.similar_min_lines", 8)
    max_group = P.opt(pol, "duplication.similar_max_group", 12)
    groups = C.similar_functions(subset, ratio,
                                 min_lines if isinstance(min_lines, int) else 8,
                                 max_group=max_group if isinstance(max_group, int) else 12)
    out = []
    for g in groups:
        # 鍵と場所は台帳の突き合わせに使う。**実行ごとに変わってはいけない。**
        # set の走査順は文字列ハッシュ次第で毎回変わるので、必ず並べてから選ぶ。
        members = sorted(g["members"], key=lambda m: (m[0], m[1]))
        names = [n for _, _, n in members]
        common = sorted(set(names), key=lambda n: (-names.count(n), n))[0]
        where = " / ".join("%s:%d %s()" % (p, ln, n) for p, ln, n in members[:4])
        if len(members) > 4:
            where += " ほか %d 件" % (len(members) - 4)
        out.append(rec(members[0][0], "similar:%s:%d" % (common, len(members)),
                       "%d 箇所に同じ形 (%.0f%%, 最大 %d 行)  %s"
                       % (len(members), g["ratio"] * 100, g["lines"], where),
                       "unify", line=members[0][1], value=len(members), members=members))
    if targets is not None:
        keep = set(targets)
        out = [r for r in out if any(p in keep for p, _, _ in r["members"])]
    return out


# ---------------------------------------------------------------- 使われない

def dead_findings(pol, data):
    entry = P.as_list(P.opt(pol, "dead.entrypoints"))
    ignore = P.as_list(P.opt(pol, "dead.ignore"))
    files = [rec(p, "dead_file", "%s がどこからも import されていない" % p, "prune")
             for p in S.dead_files(data, P.layers(pol), entry, ignore)]
    syms = []
    if P.opt(pol, "dead.symbols", True):
        syms = [rec(p, "dead_symbol:" + n,
                    "%s:%d %s() は定義だけで呼ばれていない" % (p, ln, n), "prune", line=ln)
                for p, ln, n in S.dead_symbols(data)]
    return files, syms
