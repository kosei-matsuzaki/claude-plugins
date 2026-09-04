"""コードを走査して数を出す。判断はしない。判断は ck.py と人がやる。

ここが答えるのは 5 つだけ:
  size      ファイル・関数の長さ、入れ子の深さ
  layers    import がどの層からどの層へ向いているか
  dupes     同じ形のコードがどこに散っているか
  dead      どこからも参照されていないファイル・定義
  comments  コメントの量と、コメントアウトされたコード
"""

import os
import re
from collections import Counter

import lang as L
from lang import BRACE as BRACE_STYLE, INDENT as INDENT_STYLE, END as END_STYLE
import policy as P

SKIP_DIRS = {
    ".git", "node_modules", "build", ".dart_tool", "Pods", "vendor", ".venv",
    "venv", "__pycache__", ".next", "dist", ".gradle", "target", ".idea",
    "coverage", ".mypy_cache", ".pytest_cache", "DerivedData", ".terraform",
    "bin", "obj", ".svelte-kit", "out",
}

DEFAULT_EXCLUDE = [
    "**/*.g.*", "**/*.freezed.*", "**/*_pb2.py", "**/*.pb.go", "**/*.generated.*",
    "**/generated/**", "**/*.min.js", "**/*.d.ts", "**/migrations/**",
]

MAX_BYTES = 1_500_000       # これより大きいファイルは生成物とみなして見ない
MAX_FUNC_SCAN = 3000        # 関数の終わりを探す行数の上限

# 「使われていない」と言ってはいけない名前。枠組みが名前で拾うもの。
ENTRY_NAMES = {
    "index", "main", "__init__", "mod", "lib", "app", "conftest", "setup",
    "page", "layout", "route", "middleware", "urls", "settings", "wsgi", "asgi",
    "__main__", "gradle", "build",
}


# ------------------------------------------------------------------ 対象集め

def scope_patterns(policy):
    inc = P.as_list(P.opt(policy, "scope.include")) or []
    exc = P.as_list(P.opt(policy, "scope.exclude"))
    return inc, (exc if exc else list(DEFAULT_EXCLUDE))


def source_files(root, policy, limit=8000):
    inc, exc = scope_patterns(policy)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.lower().endswith(L.EXTS):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if inc and not P.matches_any(rel, inc):
                continue
            if P.matches_any(rel, exc):
                continue
            try:
                if os.path.getsize(full) > MAX_BYTES:
                    continue
            except OSError:
                continue
            found.append(rel)
            if len(found) >= limit:
                return sorted(found)
    return sorted(found)


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None


# ---------------------------------------------------------------- 1 ファイル

def stmt_starts(rows):
    """その行が文の先頭か。かっこが閉じていない途中の行を入れ子と数えないため。

    複数行に割った関数呼び出しの引数は深く字下げされるが、入れ子ではない。
    これを除かないと、素直に書いたコードが「7 段」に見える。
    """
    out, bal = [], 0
    for kind, code in rows:
        out.append(bal == 0)
        if kind == "code":
            bal += sum(code.count(c) for c in "([{") - sum(code.count(c) for c in ")]}")
            bal = max(bal, 0)
    return out


def indent_unit(rows, starts):
    """そのファイルの字下げ幅。python の入れ子を数えるのに要る。"""
    widths = Counter()
    prev = 0
    for i, (kind, code) in enumerate(rows):
        if kind != "code" or not starts[i]:
            continue
        cur = len(code) - len(code.lstrip(" "))
        if cur > prev:
            widths[cur - prev] += 1
        prev = cur
    return widths.most_common(1)[0][0] if widths else 4


def _body_end(ctx, i, base):
    """関数の本体がどこで終わるか。言語の閉じかたごとに数え方が違う。

    波かっこは深さが 0 に戻るところ、python は字下げが戻るところ、
    ruby は同じ深さの end。返すのは (終わりの行, いちばん深いところ)。
    """
    kinds, lines, starts = ctx["kinds"], ctx["lines"], ctx["starts"]
    spec, unit = ctx["spec"], ctx["unit"]
    n, end, depth = len(lines), i, 1
    if spec["style"] == BRACE_STYLE:
        level = 0
        for j in range(i, min(n, i + MAX_FUNC_SCAN)):
            if kinds[j] != "code":
                continue
            level += lines[j].count("{") - lines[j].count("}")
            depth = max(depth, level)
            end = j
            if level <= 0 and j > i:
                break
        return end, depth
    for j in range(i + 1, min(n, i + MAX_FUNC_SCAN)):
        code = lines[j]
        ind = len(code) - len(code.lstrip(" "))
        if kinds[j] == "blank" and spec["style"] == INDENT_STYLE:
            continue
        if kinds[j] == "code" and starts[j]:
            if spec["style"] == INDENT_STYLE and ind <= base:
                break
            depth = max(depth, 1 + (ind - base) // max(unit, 1))
            if spec["style"] == END_STYLE and code.strip() == "end" and ind <= base:
                return j, depth
        end = j
    return end, depth


def functions(rows, spec, unit, starts):
    """関数の一覧。開始行 / 終了行 / 長さ / 入れ子の深さ / 引数の数。"""
    out, n = [], len(rows)
    lines = [code for _, code in rows]
    kinds = [kind for kind, _ in rows]
    ctx = {"kinds": kinds, "lines": lines, "starts": starts, "spec": spec, "unit": unit}
    taken = [False] * n
    for i in range(n):
        if kinds[i] != "code" or taken[i]:
            continue
        m = None
        for pat in spec["func"]:
            m = pat.match(lines[i])
            if m:
                break
        if not m:
            continue
        base = len(m.groupdict().get("i") or "")
        end, depth = _body_end(ctx, i, base)
        sig = lines[i]
        params, open_paren = 0, sig.find("(")
        if open_paren >= 0 and sig.rfind(")") > open_paren:
            inner = sig[open_paren + 1:sig.rfind(")")]
            params = len([x for x in inner.split(",") if x.strip()])
        for j in range(i, end + 1):
            taken[j] = True
        out.append({
            "name": m.groupdict().get("n") or "?", "start": i + 1, "end": end + 1,
            "lines": end - i + 1, "depth": max(depth - 1, 0), "params": params,
        })
    return out


COMMENTED_CODE = re.compile(r"[;{}]\s*$|^\s*(?:def |class |function |const |let |var |if |for |return |import |from |public |private )")


# 文字列の中の補間。`'${formatDuration(d)}空き'` のように、**そこでしか呼ばれない**
# 関数がある。中身を落としたまま数えると「どこからも呼ばれていない」と誤り、
# prune が動くコードを消しにいく。名前が増えても指摘は減る方向にしか効かない。
_INTERP = re.compile(r"\$\{([^{}]{1,200})\}|\\\(([^()]{1,200})\)|\$([A-Za-z_][A-Za-z0-9_]*)")


def _interpolated(raw):
    out = []
    for line in raw:
        for a, b, c in _INTERP.findall(line):
            out += re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", a or b or c or "")
    return out


def analyze(root, rel):
    """1 ファイルの数え上げ。読めなければ None。"""
    spec = L.spec_for(rel)
    text = read(root, rel)
    if spec is None or text is None:
        return None
    rows = L.classify(text, spec)
    raw = text.splitlines()
    starts = stmt_starts(rows)
    unit = indent_unit(rows, starts)
    counts = Counter(kind for kind, _ in rows)
    code_lines = [(i + 1, re.sub(r"\s+", " ", code).strip())
                  for i, (kind, code) in enumerate(rows) if kind == "code"]

    imports = []
    for i, (kind, _) in enumerate(rows):
        if kind == "blank":
            continue
        for pat in spec["imports"]:
            m = pat.search(raw[i]) if i < len(raw) else None
            if m:
                imports.append(m.group(1))

    # 連続したコメントの塊。長すぎるものと、コードのコメントアウトを見つける。
    blocks, run = [], None
    for i, (kind, _) in enumerate(rows):
        if kind == "comment":
            if run is None:
                run = [i + 1, i + 1, 0]
            run[1] = i + 1
            body = raw[i].strip() if i < len(raw) else ""
            for tok in spec["line"] + [b[0] for b in spec["block"]]:
                if body.startswith(tok):
                    body = body[len(tok):].strip()
                    break
            if body and COMMENTED_CODE.search(body):
                run[2] += 1
        else:
            if run:
                blocks.append(tuple(run))
            run = None
    if run:
        blocks.append(tuple(run))

    return {
        "path": rel, "lang": spec["name"], "total": len(rows),
        "code": counts.get("code", 0), "comment": counts.get("comment", 0),
        "blank": counts.get("blank", 0),
        "funcs": functions(rows, spec, unit, starts),
        "imports": imports, "code_lines": code_lines, "blocks": blocks,
        "names": (
            re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", " ".join(c for _, c in code_lines))
            + _interpolated(raw)),
    }


# ------------------------------------------------------------------ 層と依存

def layer_of(rel, layers):
    for layer in layers:
        if P.matches_any(rel, layer["path"]):
            return layer
    return None


def build_index(files):
    """import 先を実ファイルへ寄せるための索引。拡張子を落とした形で引く。

    3 段で引く: ファイル名そのもの → パスの末尾 → ディレクトリ
    (go や java のように、パッケージのまとまりを import する言語のため)。
    """
    by_stem, by_tail, by_dir = {}, {}, {}
    for rel in files:
        base = os.path.basename(rel)
        stem = rel[:rel.rfind(".")] if "." in base else rel
        keys = [stem]
        if os.path.basename(stem) in ("index", "__init__", "mod"):
            keys.append(os.path.dirname(stem))
        for key in keys:
            by_stem.setdefault(key, []).append(rel)
            parts = key.split("/")
            for i in range(1, len(parts)):
                by_tail.setdefault("/".join(parts[i:]), []).append(rel)
        by_dir.setdefault(os.path.dirname(rel), []).append(rel)
    return by_stem, by_tail, by_dir


DOTTED_PACKAGES = ("java", "kotlin", "scala", "python", "csharp")
_ALIAS = re.compile(r"^(?:@|~|#|\$lib|src|lib|app|packages|crate)/")


def _trimmed(body):
    """先頭のセグメントを落としながら候補を作る。

    go の example.com/app/pkg/util や java の com.example.domain.User のように、
    import の頭にはリポジトリのパスに無い接頭辞が付く。2 セグメント以上は残す。
    """
    parts = [p for p in body.split("/") if p]
    out = []
    for i in range(len(parts)):
        if i and len(parts) - i < 2:
            break
        out.append("/".join(parts[i:]))
    return out


def resolve(spec_str, from_rel, index, langname=""):
    """import の文字列から、リポジトリ内のファイルを引く。外部パッケージなら空。"""
    by_stem, by_tail, by_dir = index
    spec_str = spec_str.strip().strip("'\"").rstrip(";")
    if not spec_str:
        return []
    here = os.path.dirname(from_rel)
    cands = []

    if spec_str.startswith("."):
        if langname == "python" and "/" not in spec_str:
            up = len(spec_str) - len(spec_str.lstrip("."))
            base = here
            for _ in range(max(up - 1, 0)):
                base = os.path.dirname(base)
            cands.append(os.path.normpath(os.path.join(base, spec_str[up:].replace(".", "/"))))
        else:
            cands.append(os.path.normpath(os.path.join(here, spec_str)))
    elif langname == "rust" and spec_str.split("::")[0] in ("self", "super"):
        parts = spec_str.split("::")
        base = here
        while parts and parts[0] in ("self", "super"):
            if parts[0] == "super":
                base = os.path.dirname(base)
            parts.pop(0)
        cands.append(os.path.normpath(os.path.join(base, "/".join(parts))))
    else:
        body = spec_str.replace("\\", "/").replace("::", "/")
        if body.startswith("package:"):                     # dart
            body = body.split("/", 1)[1] if "/" in body else body
        # ドットでパッケージを区切るのは一部の言語だけ。dart の
        # `import 'docs_screen.dart';` を変換すると docs_screen/dart になり、
        # **同じディレクトリの import が一度も解決しなくなる。**
        if "/" not in body and langname in DOTTED_PACKAGES:
            body = body.replace(".", "/")
        cands += _trimmed(body)
        stripped = _ALIAS.sub("", body)
        if stripped != body:
            cands += _trimmed(stripped)

    cands = [c.replace(os.sep, "/").rstrip("/") for c in cands]
    for table, cap in ((by_stem, 3), (by_tail, 2), (by_dir, 5)):
        for cand in cands:
            for key in (cand, re.sub(r"\.\w+$", "", cand)):
                hit = table.get(key)
                if not hit or len(hit) > cap:
                    continue
                # 言語をまたぐ一致は外部パッケージの空似。捨てる。
                same = [h for h in hit if (L.spec_for(h) or {}).get("name") == langname]
                if same:
                    return _nearest(same, here)
    return []


def _nearest(hits, here):
    """同じ名前のファイルが複数あるとき、呼んでいる側に近いほうを採る。

    `import policy` のような裸の名前は、どのディレクトリにもありうる。
    近さで選ばないと、隣のパッケージへの依存をでっち上げてしまう。
    """
    if len(hits) < 2:
        return hits
    same_dir = [h for h in hits if os.path.dirname(h) == here]
    if same_dir:
        return same_dir
    here_parts = here.split("/")

    def shared(path):
        parts = os.path.dirname(path).split("/")
        n = 0
        while n < min(len(parts), len(here_parts)) and parts[n] == here_parts[n]:
            n += 1
        return n

    best = max(shared(h) for h in hits)
    return [h for h in hits if shared(h) == best]


def edges(root, data, layers):
    """(from, to, from層, to層) の一覧と、層に属さないファイル。"""
    index = build_index(list(data))
    out, homeless = [], []
    for rel, info in data.items():
        src_layer = layer_of(rel, layers)
        if layers and src_layer is None:
            homeless.append(rel)
        for spec_str in info["imports"]:
            for target in resolve(spec_str, rel, index, info["lang"]):
                if target == rel:
                    continue
                out.append((rel, target, src_layer, layer_of(target, layers)))
    return out, homeless


def violations(edge_list):
    """層の決まりに反している依存。理由つきで返す。"""
    bad = []
    for src, dst, sl, dl in edge_list:
        if sl is None or dl is None:
            continue
        if sl["name"] == dl["name"]:
            depth = sl.get("isolate")
            if depth and src.split("/")[:depth] != dst.split("/")[:depth]:
                bad.append((src, dst, "%s の中で別々に分かれているもの同士は依存させない" % sl["name"]))
            continue
        if dl["name"] not in sl["allow"]:
            bad.append((src, dst, "%s は %s に依存できない" % (sl["name"], dl["name"])))
    return bad


# ---------------------------------------------------------------- 使われない

def dead_files(data, layers, entrypoints, ignore):
    """どこからも import されていないファイル。枠組みが名前で拾うものは除く。"""
    index = build_index(list(data))
    referenced = set()
    for rel, info in data.items():
        for spec_str in info["imports"]:
            for target in resolve(spec_str, rel, index, info["lang"]):
                if target != rel:
                    referenced.add(target)
    out = []
    for rel in sorted(data):
        if rel in referenced or P.matches_any(rel, entrypoints) or P.matches_any(rel, ignore):
            continue
        base = os.path.basename(rel)
        stem = base[:base.rfind(".")] if "." in base else base
        if stem.lower() in ENTRY_NAMES:
            continue
        out.append(rel)
    return out


def dead_symbols(data, top=20):
    """定義してあるのに、どこでも呼ばれていない名前。動的に呼ぶものは見抜けない。"""
    freq = Counter()
    for info in data.values():
        freq.update(info["names"])
    out = []
    for rel in sorted(data):
        for fn in data[rel]["funcs"]:
            name = fn["name"]
            if len(name) < 4 or name.lower() in ENTRY_NAMES or name.startswith("_"):
                continue
            if freq[name] <= 1:
                out.append((rel, fn["start"], name))
    return out[:top]
