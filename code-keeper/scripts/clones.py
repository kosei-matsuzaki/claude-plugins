"""同じ形のコードを見つける。行がそろっているものと、そろっていないもの。

  duplicates         行がそのまま重なっているところ (文字列と数値の中身は無視)
  similar_functions  形は似ているが行はそろっていない関数のかたまり

後者が要るのは、共通化できるものの多くが**完全一致しない**から。
FE のボタンのように、骨組みは同じで文言と色だけ違うものは前者では見つからない。

**どちらも「候補」しか出せない。** まとめてよいかは、同じ理由で変わるかどうかで、
それはコードを読まないと決まらない。決めるのは Claude と人。
"""

import re

def duplicates(data, min_lines=8, max_pairs=200000, top=25):
    """同じ形のコードの塊。文字列と数字の中身は無視して比べる。"""
    files = sorted(data)
    windows = {}
    for fi, rel in enumerate(files):
        norms = [t for _, t in data[rel]["code_lines"]]
        for k in range(len(norms) - min_lines + 1):
            win = norms[k:k + min_lines]
            if len(set(win)) < max(2, min_lines // 2):
                continue          # `}` の並びのような定型は数えない
            windows.setdefault(hash("\n".join(win)), []).append((fi, k))

    pairs = set()
    for occ in windows.values():
        if len(occ) < 2 or len(occ) > 8:
            continue              # 8 箇所以上に出るものは定型文。共通化の対象にしない
        for a in range(len(occ)):
            for b in range(a + 1, len(occ)):
                (f1, k1), (f2, k2) = occ[a], occ[b]
                if f1 == f2 and abs(k1 - k2) < min_lines:
                    continue
                pairs.add((f1, k1, f2, k2))
                if len(pairs) > max_pairs:
                    return []     # 定型だらけ。ここで諦める
    out = []
    for (f1, k1, f2, k2) in pairs:
        if (f1, k1 - 1, f2, k2 - 1) in pairs:
            continue              # 途中。塊の頭だけを見る
        n = min_lines
        while (f1, k1 + n - min_lines + 1, f2, k2 + n - min_lines + 1) in pairs:
            n += 1
        a, b = files[f1], files[f2]
        la = data[a]["code_lines"]
        lb = data[b]["code_lines"]
        if k1 + n - 1 >= len(la) or k2 + n - 1 >= len(lb):
            continue
        out.append({
            "lines": n,
            "a": (a, la[k1][0], la[k1 + n - 1][0]),
            "b": (b, lb[k2][0], lb[k2 + n - 1][0]),
        })
    out.sort(key=lambda d: -d["lines"])
    seen, kept = set(), []
    for d in out:
        key = (d["a"][0], d["b"][0])
        if key in seen:
            continue      # 同じ組は最も長い塊だけ出す
        seen.add(key)
        kept.append(d)
        if len(kept) >= top:
            break
    return kept


# 骨組みだけを見るために残す語。これ以外の名前はぜんぶ `_` に潰す。
# 言語をまたいで共通のものだけ。名前が違っても形が同じなら似ていると見なすため。
STRUCT_WORDS = {
    "if", "else", "elif", "for", "while", "do", "switch", "case", "default",
    "return", "break", "continue", "try", "catch", "except", "finally",
    "throw", "raise", "new", "delete", "class", "struct", "enum", "interface",
    "def", "fn", "func", "function", "const", "let", "var", "val", "static",
    "public", "private", "protected", "async", "await", "yield", "import",
    "from", "export", "in", "of", "is", "as", "not", "and", "or", "with",
    "true", "false", "null", "nil", "none", "self", "this", "super",
}

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\sA-Za-z0-9_]")
GRAM = 4                  # 何トークンつなげて形を見るか
MAX_FUNCS = 4000
COMMON_GRAM = 60          # これより多くの関数に出る形は定型。数えない
MAX_PAIRS = 300000


def skeleton(text):
    """名前とリテラルを潰して、骨組みだけのトークン列にする。

    `PrimaryButton` も `IconButton` も `_` になる。文言と色だけが違う
    ボタンのような「行はそろわないが同じ形」を拾うため。
    """
    out = []
    for tok in _TOKEN.findall(text):
        first = tok[0]
        if first.isdigit():
            out.append("0")
        elif first.isalpha() or first == "_":
            out.append(tok if tok.lower() in STRUCT_WORDS else "_")
        else:
            out.append(tok)
    return out


def _grams(tokens):
    return {hash(tuple(tokens[i:i + GRAM])) for i in range(len(tokens) - GRAM + 1)}


def similar_functions(data, threshold=0.75, min_lines=8, top=20, max_group=12):
    """形が似ている関数のかたまり。行がそろっていなくても拾う。

    「小さいほうの何割が相手に入っているか」で見る。Jaccard だと、
    片方に付け足しがあるだけで似ていないことになってしまう。

    組ではなく**かたまり**で返す。同じ形の確認ダイアログが 5 箇所にあるとき、
    10 組の一覧を見せられても困る。「5 箇所にある」と言われたほうが直せる。

    max_group より大きいかたまりは捨てる。Flutter の build や React の
    コンポーネントは、枠組みがそう書けと言っているだけで、共通化の余地ではない。

    **似ていることと、まとめてよいことは別。** ここが出すのは
    「並べて読む価値がある」ところまでで、決めるのは読んだ人。
    """
    units = _skeletons(data, min_lines)
    index = {}
    for i, unit in enumerate(units):
        for g in unit["grams"]:
            index.setdefault(g, []).append(i)

    shared = {}
    for occ in index.values():
        if len(occ) > COMMON_GRAM:
            continue          # どこにでも出る形。定型なので数えない
        for a in range(len(occ)):
            for b in range(a + 1, len(occ)):
                pair = (occ[a], occ[b])
                shared[pair] = shared.get(pair, 0) + 1
                if len(shared) > MAX_PAIRS:
                    return []  # 定型だらけ。ここで諦める

    parent = list(range(len(units)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    scores = {}
    for (i, j), count in shared.items():
        if count < GRAM:
            continue
        gi, gj = units[i]["grams"], units[j]["grams"]
        small, large = min(len(gi), len(gj)), max(len(gi), len(gj))
        if small < GRAM or small / float(large) < 0.4:
            continue          # 大きさが違いすぎる組。短い関数がたまたま埋もれただけ
        ratio = len(gi & gj) / float(small)
        if ratio < threshold:
            continue
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
        key = find(i)
        scores.setdefault(key, []).append(ratio)

    groups = {}
    for i in range(len(units)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for root_id, members in groups.items():
        if len(members) < 2 or len(members) > max_group:
            continue          # 大きすぎるかたまりは枠組みの書き方 (Flutter の build など)
        got = [units[m] for m in members]
        ratios = scores.get(root_id) or [threshold]
        out.append({
            "ratio": sum(ratios) / len(ratios),
            "lines": max(u["lines"] for u in got),
            "members": sorted((u["path"], u["start"], u["name"]) for u in got),
        })
    # 数が多いもの・大きいものから。直したときに効くのはそこ。
    out.sort(key=lambda d: (-len(d["members"]), -d["lines"], -d["ratio"]))
    return out[:top]


def _skeletons(data, min_lines):
    """関数ごとの骨組み。長さが足りないものは見ない。"""
    units = []
    for rel in sorted(data):
        lines = data[rel]["code_lines"]
        for fn in data[rel]["funcs"]:
            body = [text for num, text in lines if fn["start"] <= num <= fn["end"]]
            if len(body) < min_lines:
                continue
            grams = _grams(skeleton(" ".join(body)))
            if len(grams) < GRAM:
                continue
            units.append({"path": rel, "start": fn["start"], "name": fn["name"],
                          "lines": len(body), "grams": grams})
            if len(units) >= MAX_FUNCS:
                return units
    return units


