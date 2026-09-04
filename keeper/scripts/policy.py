"""規約ファイルの読み込みとパス照合。標準ライブラリだけで動く。

規約は `.claude/policy.yml` 1 つに `roles:` / `docs:` / `code:` を持つ。
以前は docs-keeper と code-keeper が別々の規約ファイルを持っていたので、
それらが残っているリポジトリでは読み込んで同じ形に合わせる (init が統合を提案する)。

書式は YAML のごく狭い部分集合しか使わない (コメント / key: value / 入れ子マップ /
'- ' リスト / インラインリスト)。PyYAML を入れずに済ませるため、小さなパーサを持つ。
"""

import os
import re

POLICY = ".claude/policy.yml"
POLICY_CANDIDATES = (POLICY, ".claude/policy.yaml")

# 統合前の規約ファイル。まだ残っているリポジトリのために読む
LEGACY = (
    ("docs", ("docs/.docs-policy.yml", "docs/.docs-policy.yaml", ".claude/docs-policy.yml")),
    ("code", (".code-policy.yml", ".code-policy.yaml", ".claude/code-policy.yml")),
)

KINDS = ("product", "tool", "library", "research")
REVENUES = ("none", "unknown", "ads", "subscription", "paid", "sponsor", "contract")

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
    """規約を持つ最も近い祖先。無ければ git のトップ、それも無ければ start。"""
    cur = os.path.abspath(start)
    while True:
        for cand in POLICY_CANDIDATES:
            if os.path.isfile(os.path.join(cur, cand)):
                return cur, os.path.join(cur, cand)
        for _, cands in LEGACY:          # 統合前の規約しか無いリポジトリも根とみなす
            for cand in cands:
                if os.path.isfile(os.path.join(cur, cand)):
                    return cur, None
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


def legacy_files(root):
    """(節の名前, パス) の一覧。統合前の規約が残っていれば出る。"""
    out = []
    for section, cands in LEGACY:
        for cand in cands:
            full = os.path.join(root, cand)
            if os.path.isfile(full):
                out.append((section, cand))
                break
    return out


# ----------------------------------------------------------------- validation

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PATHY = re.compile(r"^[A-Za-z0-9._*?/{},\-]+$")


def _bad_roles(roles):
    if not isinstance(roles, list):
        return "roles はリストで書く"
    seen = set()
    for i, role in enumerate(roles):
        if not isinstance(role, dict):
            return "roles[%d] は name / why のマップで書く" % i
        name = role.get("name")
        if not isinstance(name, str) or not _SLUG.match(name):
            return "roles[%d].name は英小文字とハイフンで書く (%r)" % (i, name)
        if name in seen:
            return "roles に %s が 2 つある" % name
        seen.add(name)
        if not role.get("why"):
            return "roles[%s] に why が無い。なぜその役が要るかを書く" % name
    return None


def _bad_layers(layers):
    if not isinstance(layers, list):
        return "code.layers はリストで書く"
    names = set()
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict) or not layer.get("name"):
            return "code.layers[%d] に name が無い" % i
        names.add(layer["name"])
        for path in as_list(layer.get("path")):
            if not isinstance(path, str) or not _PATHY.match(path):
                return "code.layers[%s].path がパスとして読めない (%r)" % (layer["name"], path)
        iso = layer.get("isolate")
        if iso is not None and (not isinstance(iso, int) or isinstance(iso, bool) or iso < 1):
            return "code.layers[%s].isolate は 1 以上の整数" % layer["name"]
    for layer in layers:
        for allowed in as_list(layer.get("allow")):
            if allowed not in names:
                return "code.layers[%s].allow に無い層 %r がある" % (layer["name"], allowed)
    return None


def _bad_watch(watch):
    if not isinstance(watch, list):
        return "docs.watch はリストで書く"
    for i, item in enumerate(watch):
        if not isinstance(item, dict):
            return "docs.watch[%d] は source / docs / why のマップで書く" % i
        for key in ("source", "docs"):
            val = item.get(key)
            if val is None or (isinstance(val, list) and not val):
                continue
            if isinstance(val, str):
                continue
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                return "docs.watch[%d].%s は文字列かそのリストで書く" % (i, key)
    return None


def validate(data):
    """規約として筋が通っているか。おかしければ理由を返す。

    書式が崩れていても parse_yaml は何かしら返してしまう。ここで弾かないと、
    壊れた規約のまま「役が足りない」「層を逸脱している」と誤って言い出す。
    """
    if not isinstance(data, dict):
        return "最上位がマップになっていない"
    if not data:
        return "中身が空"

    proj = data.get("project")
    if proj is not None:
        if not isinstance(proj, dict):
            return "project はマップで書く"
        if proj.get("kind") is not None and proj["kind"] not in KINDS:
            return "project.kind は %s のどれか (%r)" % (" / ".join(KINDS), proj["kind"])
        if proj.get("revenue") is not None and proj["revenue"] not in REVENUES:
            return "project.revenue は %s のどれか (%r)" % (" / ".join(REVENUES), proj["revenue"])

    for key, check in (("roles", _bad_roles),):
        if data.get(key) is not None:
            bad = check(data[key])
            if bad:
                return bad

    plugins = data.get("plugins")
    if plugins is not None and not isinstance(plugins, list):
        return "plugins は名前のリストで書く"

    docs = data.get("docs")
    if docs is not None:
        if not isinstance(docs, dict):
            return "docs はマップで書く"
        if docs.get("index") is not None and not isinstance(docs["index"], str):
            return "docs.index は 1 つのパスで書く"
        if docs.get("watch") is not None:
            bad = _bad_watch(docs["watch"])
            if bad:
                return bad
        for i, item in enumerate(docs.get("layout") or []):
            path = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path, str) or not _PATHY.match(path):
                return "docs.layout[%d] の path がパスとして読めない (%r)" % (i, path)

    code = data.get("code")
    if code is not None:
        if not isinstance(code, dict):
            return "code はマップで書く"
        if code.get("layers") is not None:
            bad = _bad_layers(code["layers"])
            if bad:
                return bad

    return None


# ------------------------------------------------------------------- loading

def load(start):
    """(root, policy_path, policy) を返す。

    `.claude/policy.yml` が無くても、統合前の規約 (docs/.docs-policy.yml /
    .code-policy.yml) があればそれを読んで同じ形に組み立てる。**黙って捨てない。**
    """
    root, path = find_root(start)
    data = {}
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                data = parse_yaml(fh.read())
        except Exception as exc:            # 壊れた規約でセッションを止めない
            return root, path, {"_error": "読み込みに失敗: %s" % exc}
        if not isinstance(data, dict):
            return root, path, {"_error": "最上位がマップになっていない"}

    for section, rel in legacy_files(root):
        if data.get(section):               # 統合ずみなら旧ファイルは見ない
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                legacy = parse_yaml(fh.read())
        except Exception:
            continue
        if isinstance(legacy, dict):
            legacy.pop("version", None)
            data[section] = legacy
            data.setdefault("_legacy", []).append(rel)

    if not path and not data:
        return root, None, None
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
    return list(val) if isinstance(val, list) else [val]


def _either(policy, dotted):
    """規約の全体を渡されても、その節だけを渡されても引けるようにする。

    数える部分 (scan / report / docs) には `code:` や `docs:` の中身だけを渡す。
    節の名前で引くと空になり、**検査が黙って動かなくなる**。
    """
    val = opt(policy, dotted)
    if val is None:
        val = opt(policy, dotted.split(".", 1)[1])
    return val or []


def roles(policy):
    return [r for r in (policy or {}).get("roles") or []
            if isinstance(r, dict) and r.get("name")]


def role_names(policy):
    return [r["name"] for r in roles(policy)]


def layers(policy):
    """code.layers を (name, paths, allow, isolate, role) に均す。"""
    out = []
    for raw in _either(policy, "code.layers"):
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        out.append({
            "name": raw["name"],
            "path": as_list(raw.get("path")),
            "allow": as_list(raw.get("allow")),
            "isolate": raw.get("isolate"),
            "role": raw.get("role") or "",
        })
    return out


def watch_rules(policy):
    out = []
    for raw in _either(policy, "docs.watch"):
        if not isinstance(raw, dict):
            continue
        out.append({
            "source": as_list(raw.get("source")),
            "docs": as_list(raw.get("docs")),
            "why": raw.get("why") or "",
        })
    return out


def layout_paths(policy):
    out = []
    for raw in _either(policy, "docs.layout"):
        if isinstance(raw, dict) and raw.get("path"):
            out.append((raw["path"], raw.get("role") or ""))
        elif isinstance(raw, str):
            out.append((raw, ""))
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


def doc_limit(policy, relpath):
    """docs.limits はパスごとの行数マップ ({CLAUDE.md: 500, default: 400})。

    code.limits (`limits.file_lines` のように種類ごと) とは形が違うので分けてある。
    """
    limits = (policy or {}).get("limits") or {}
    if not isinstance(limits, dict):
        return None
    for key, val in limits.items():
        if key == "default":
            continue
        if key == relpath or glob_to_re(key).match(relpath):
            return val
    return limits.get("default")
