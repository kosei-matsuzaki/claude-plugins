"""code-keeper: 規約ファイルの読み込みとパス照合。標準ライブラリだけで動く。

規約ファイルは YAML のごく狭い部分集合しか使わない(コメント / key: value /
入れ子マップ / '- ' リスト / インラインリスト)。PyYAML を入れずに済ませるため、
ここに小さなパーサを持っている。docs-keeper の policy.py と同じ書式。
"""

import os
import re

POLICY_CANDIDATES = (
    ".code-policy.yml",
    ".code-policy.yaml",
    ".claude/code-policy.yml",
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
    if re.fullmatch(r"-?\d*\.\d+", text):
        return float(text)
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
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1]
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

_RE_CACHE = {}


def glob_to_re(pattern):
    """`**` はディレクトリ境界をまたぐ。末尾 `/` はそのディレクトリ配下すべて。"""
    cached = _RE_CACHE.get(pattern)
    if cached:
        return cached
    src = pattern + "**" if pattern.endswith("/") else pattern
    out, i = ["^"], 0
    while i < len(src):
        if src.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif src.startswith("**", i):
            out.append(".*")
            i += 2
        elif src[i] == "*":
            out.append("[^/]*")
            i += 1
        elif src[i] == "?":
            out.append("[^/]")
            i += 1
        elif src[i] == "{":
            end = src.find("}", i)
            if end < 0:
                out.append(re.escape(src[i]))
                i += 1
                continue
            alts = src[i + 1:end].split(",")
            out.append("(?:%s)" % "|".join(re.escape(a) for a in alts))
            i = end + 1
        else:
            out.append(re.escape(src[i]))
            i += 1
    out.append("$")
    compiled = re.compile("".join(out))
    _RE_CACHE[pattern] = compiled
    return compiled


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

_PATHY = re.compile(r"^[A-Za-z0-9._*?/{},\-]+$")


def _validate_layers(layers):
    """層の書きかた。ここが崩れたまま動くと guard が誤爆するので、先に弾く。"""
    if not isinstance(layers, list):
        return "layers はリストで書く"
    names = set()
    for i, item in enumerate(layers):
        if not isinstance(item, dict):
            return "layers[%d] は name / path / allow のマップで書く" % i
        name = item.get("name")
        if not isinstance(name, str) or not name:
            return "layers[%d] に name が無い" % i
        if name in names:
            return "層の名前 %s が重複している" % name
        names.add(name)
        paths = as_list(item.get("path"))
        if not paths:
            return "layers[%s].path が無い" % name
        bad = [p for p in paths if not isinstance(p, str) or not _PATHY.match(p)]
        if bad:
            return "layers[%s].path がパスとして読めない (%r)" % (name, bad[0])
        iso = item.get("isolate")
        if iso is not None and (not isinstance(iso, int) or isinstance(iso, bool)):
            return "layers[%s].isolate はセグメント数(整数)で書く" % name
    for item in layers:
        unknown = [a for a in as_list(item.get("allow")) if a not in names]
        if unknown:
            return "layers[%s].allow に無い層 %r が書いてある" % (item.get("name"), unknown[0])
    return None


def _validate_limits(limits):
    if not isinstance(limits, dict):
        return "limits はマップで書く"
    for key, val in limits.items():
        vals = list(val.values()) if isinstance(val, dict) else [val]
        for num in vals:
            if not isinstance(num, int) or isinstance(num, bool):
                return "limits.%s は数か、パターンごとのマップで書く" % key
    return None


def validate(data):
    """規約として筋が通っているか。おかしければ理由を返す。

    書式が崩れていても parse_yaml は何かしら返してしまうので、
    ここで弾かないと、壊れた規約のまま guard が誤爆する。
    """
    if not isinstance(data, dict):
        return "最上位がマップになっていない"
    if not data:
        return "中身が空"

    for key in ("include", "exclude"):
        val = opt(data, "scope." + key)
        if val is not None and not (isinstance(val, list) and all(isinstance(v, str) for v in val)):
            return "scope.%s はパターンのリストで書く" % key

    for checker, val in ((_validate_layers, data.get("layers")),
                         (_validate_limits, data.get("limits"))):
        if val is not None:
            problem = checker(val)
            if problem:
                return problem

    for key in ("comments.min_ratio", "comments.max_ratio"):
        val = opt(data, key)
        if val is not None and not isinstance(val, (int, float)):
            return "%s は割合(0.05 のような数)で書く" % key

    min_lines = opt(data, "duplication.min_lines")
    if min_lines is not None and (not isinstance(min_lines, int)
                                  or isinstance(min_lines, bool) or min_lines < 4):
        return "duplication.min_lines は 4 以上の整数で書く"
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

def opt(policy, dotted, default=None):
    node = policy or {}
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return default if node is None else node


def as_list(val):
    if val is None:
        return []
    return [val] if isinstance(val, str) else list(val)


def layers(policy):
    out = []
    for raw in (policy or {}).get("layers") or []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        out.append({
            "name": raw["name"],
            "path": as_list(raw.get("path")),
            "allow": as_list(raw.get("allow")),
            "role": raw.get("role") or "",
            "isolate": raw.get("isolate") if isinstance(raw.get("isolate"), int) else None,
        })
    return out


def limit_for(policy, key, relpath, default=None):
    """limits.<key> は数そのものか、パターンごとのマップ({default: N, "src/ui/**": M})。"""
    val = opt(policy, "limits." + key)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, dict):
        for pat, num in val.items():
            if pat == "default":
                continue
            if pat == relpath or glob_to_re(pat).match(relpath):
                return num
        if isinstance(val.get("default"), int):
            return val["default"]
    return default
