"""docs-keeper: 規約ファイルの読み込みとパス照合。標準ライブラリだけで動く。

規約ファイルは YAML のごく狭い部分集合しか使わない(コメント / key: value /
入れ子マップ / '- ' リスト / インラインリスト)。PyYAML を入れずに済ませるため、
ここに小さなパーサを持っている。
"""

import os
import re

POLICY_CANDIDATES = (
    "docs/.docs-policy.yml",
    "docs/.docs-policy.yaml",
    ".claude/docs-policy.yml",
)


# ---------------------------------------------------------------- YAML subset

def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(p) for p in _split_inline(inner)]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    low = text.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _split_inline(text):
    parts, buf, quote = [], [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _lines(text):
    out = []
    for raw in text.splitlines():
        s = _strip_comment(raw)
        if not s.strip():
            continue
        out.append((len(s) - len(s.lstrip(" ")), s.strip()))
    return out


def _parse(lines, i, indent):
    if lines[i][1].startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or content.startswith("- "):
            break
        key, sep, rest = content.partition(":")
        if not sep:
            break
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            out[key], i = _parse(lines, i, lines[i][0])
        elif i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
            out[key], i = _parse_list(lines, i, indent)
        else:
            out[key] = None
    return out, i


def _parse_list(lines, i, indent):
    out = []
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or not content.startswith("- "):
            break
        body = content[2:].strip()
        sub, j = [], i + 1
        while j < len(lines) and lines[j][0] > indent:
            sub.append(lines[j])
            j += 1
        if ":" in body and not body.startswith("[") and not body.startswith('"'):
            item, _ = _parse_map([(indent + 2, body)] + sub, 0, indent + 2)
            out.append(item)
        elif sub:
            val, _ = _parse(sub, 0, sub[0][0])
            out.append(val)
        else:
            out.append(_scalar(body))
        i = j
    return out, i


def parse_yaml(text):
    lines = _lines(text)
    if not lines:
        return {}
    val, _ = _parse(lines, 0, lines[0][0])
    return val


# -------------------------------------------------------------- glob matching

def glob_to_re(pattern):
    """`**` はディレクトリ境界をまたぐ。末尾 `/` はそのディレクトリ配下すべて。"""
    if pattern.endswith("/"):
        pattern += "**"
    out, i = ["^"], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def matches_any(path, patterns):
    return any(glob_to_re(p).match(path) for p in (patterns or []))


# ------------------------------------------------------------------ discovery

def find_root(start):
    """規約ファイルを持つ最も近い祖先。無ければ git のトップ、それも無ければ start。"""
    cur = os.path.abspath(start)
    while True:
        for cand in POLICY_CANDIDATES:
            if os.path.isfile(os.path.join(cur, cand)):
                return cur, os.path.join(cur, cand)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur, None
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start), None
        cur = parent


# ----------------------------------------------------------------- validation

_PATHY = re.compile(r"^[A-Za-z0-9._*?/\-]+$")


def validate(data):
    """規約として筋が通っているか。おかしければ理由を返す。

    書式が崩れていても parse_yaml は何かしら返してしまうので、
    ここで弾かないと、壊れた規約のまま guard が誤爆する。
    """
    if not isinstance(data, dict):
        return "最上位がマップになっていない"
    if not data:
        return "中身が空"

    index = data.get("index")
    if index is not None and not isinstance(index, str):
        return "index は 1 つのパスで書く"

    layout = data.get("layout")
    if layout is not None:
        if not isinstance(layout, list):
            return "layout はリストで書く"
        for i, item in enumerate(layout):
            path = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path, str) or not _PATHY.match(path):
                return "layout[%d] の path がパスとして読めない (%r)" % (i, path)

    watch = data.get("watch")
    if watch is not None:
        if not isinstance(watch, list):
            return "watch はリストで書く"
        for i, item in enumerate(watch):
            if not isinstance(item, dict):
                return "watch[%d] は source / docs / why のマップで書く" % i
            for key in ("source", "docs"):
                val = item.get(key)
                if val is None or (isinstance(val, list) and not val):
                    continue  # 空欄は雛形のまま。無視する
                if isinstance(val, str):
                    continue
                if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                    return "watch[%d].%s は文字列かそのリストで書く" % (i, key)

    limits = data.get("limits")
    if limits is not None:
        if not isinstance(limits, dict):
            return "limits はマップで書く"
        for key, val in limits.items():
            if not isinstance(val, int) or isinstance(val, bool):
                return "limits[%s] は行数(整数)で書く" % key

    return None


def load(start):
    """(root, policy_path, policy_dict) を返す。規約が無ければ policy は None。"""
    root, path = find_root(start)
    if not path:
        return root, None, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = parse_yaml(fh.read())
    except Exception as exc:  # 壊れた規約でセッションを止めない
        return root, path, {"_error": "読み込みに失敗: %s" % exc}
    problem = validate(data)
    if problem:
        return root, path, {"_error": problem}
    return root, path, data


# --------------------------------------------------------------- policy views

def watch_rules(policy):
    rules = []
    for raw in (policy or {}).get("watch") or []:
        if not isinstance(raw, dict):
            continue
        src, doc = raw.get("source"), raw.get("docs")
        rules.append({
            "source": [src] if isinstance(src, str) else list(src or []),
            "docs": [doc] if isinstance(doc, str) else list(doc or []),
            "why": raw.get("why") or "",
        })
    return rules


def layout_paths(policy):
    out = []
    for raw in (policy or {}).get("layout") or []:
        if isinstance(raw, dict) and raw.get("path"):
            out.append((raw["path"], raw.get("role") or ""))
        elif isinstance(raw, str):
            out.append((raw, ""))
    return out


def limit_for(policy, relpath):
    limits = (policy or {}).get("limits") or {}
    if not isinstance(limits, dict):
        return None
    for key, val in limits.items():
        if key == "default":
            continue
        if key == relpath or glob_to_re(key).match(relpath):
            return val
    return limits.get("default")


def opt(policy, dotted, default=None):
    node = policy or {}
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return default if node is None else node
