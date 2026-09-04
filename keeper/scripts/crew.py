""".claude/ の棚卸しと、生成物が腐っていないかの照合。

生成した .claude/ が腐る一番の形は、消えたディレクトリや無くなったコマンドを
CLAUDE.md と agent が指し続けることで、これは読んだ Claude を静かに間違わせる
(存在しないパスを探し、無いコマンドを勧める)。人は気づけないが、機械は数えられる。

見るのはパスとコマンドの実在だけ。中身が正しいかは読まないと分からないので、
そちらは check の報告を受けて Claude がやる。

生成したときの姿 (指紋) も控える。腐ったことに気づける手がかりは 2 つしかない —
**生成物に手が入ったか**と、**土台のリポジトリが変わったか**。
"""

import fnmatch
import glob as globlib
import hashlib
import json
import os
import re

CLAUDE_DIR = ".claude"
AGENT_DIR = ".claude/agents"
COMMAND_DIR = ".claude/commands"
SKILL_DIR = ".claude/skills"
SETTINGS = (".claude/settings.json", ".claude/settings.local.json")

# keeper が要るときに作るもの。まだ無いのは正常なので参照切れと言わない
_ON_DEMAND = (".claude/judgments.yml", ".claude/manifest.json")

# そのまま写す規約。プラグイン側と中身が違えば、古いか手が入っている
COPIED_SKILLS = ("flat-view", "claude-md", "docs-style", "code-comments")

# パスとして拾う形。日本語混じり (「1日目/2日目」) や package: のような
# スキーム付きは、スラッシュを含んでいてもパスではない。
_PATHY = re.compile(r"^[A-Za-z0-9._*?/-]+$")
# 先頭が "/" のものは絶対パスかスラッシュコマンドで、どちらも相対の参照ではない
_SKIP_REF = re.compile(r"^(/|-|\.\.\.$)")

SKIP_DIRS = {
    ".git", "node_modules", "build", ".dart_tool", "Pods", "vendor",
    ".venv", "venv", "__pycache__", ".next", "dist", ".gradle", "target",
}
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_TICKED = re.compile(r"`([^`\n]{2,120})`")
_SLASH_CMD = re.compile(r"(?<![\w/])/([a-z][a-z0-9-]*):([a-z][a-z0-9-]*)")
_HOLE = re.compile(r"\{\{\s*([^{}\n]{1,60}?)\s*\}\}")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _md_files(root, subdir):
    base = os.path.join(root, subdir)
    if not os.path.isdir(base):
        return []
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def line_count(root, rel_path):
    text = _read(os.path.join(root, rel_path))
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


# ---------------------------------------------------------------------- 棚卸し

def scan(root):
    agents = _md_files(root, AGENT_DIR)
    commands = _md_files(root, COMMAND_DIR)
    skills = [
        p for p in _md_files(root, SKILL_DIR)
        if os.path.basename(p) == "SKILL.md"
    ]
    claude_md = "CLAUDE.md" if os.path.isfile(os.path.join(root, "CLAUDE.md")) else None
    return {
        "claude_md": claude_md,
        "claude_md_lines": line_count(root, claude_md) if claude_md else 0,
        "agents": agents,
        "commands": commands,
        "skills": skills,
        "settings": [s for s in SETTINGS if os.path.isfile(os.path.join(root, s))],
        "has_dir": os.path.isdir(os.path.join(root, CLAUDE_DIR)),
    }


def hook_events(root):
    """settings.json に仕掛かっているフックの一覧。(ファイル, イベント, 件数)。"""
    out = []
    for rel_path in SETTINGS:
        full = os.path.join(root, rel_path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            out.append((rel_path, "読めない", 0))
            continue
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            continue
        for event, entries in sorted(hooks.items()):
            n = sum(len(e.get("hooks") or []) for e in entries if isinstance(e, dict))
            out.append((rel_path, event, n))
    return out


# -------------------------------------------------------------------- 参照切れ

def _candidate_refs(text):
    """本文からパスらしきものを拾う。スラッシュを含むものだけ見る。

    `git status` のようなシェルの断片、URL、`1日目/2日目` のような日本語、
    `package:foo/bar.dart` のようなスキーム付きを拾うと、実在しないと言い続けて
    信用されなくなる。**取りこぼすほうを選ぶ。**
    """
    refs = set()
    for raw in _LINK.findall(text) + _TICKED.findall(text):
        ref = raw.split("#")[0].strip().rstrip(",")
        if not ref or "/" not in ref or _SKIP_REF.search(ref):
            continue
        if not _PATHY.match(ref):
            continue
        refs.add(ref)
    return refs


def _repo_index(root):
    """リポジトリにある全パス。末尾一致で照合するために持つ。"""
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        base = os.path.relpath(dirpath, root).replace(os.sep, "/")
        base = "" if base == "." else base + "/"
        for name in list(dirnames) + filenames:
            out.add(base + name)
    return out


def _exists(root, ref, index):
    """実在するか。**リポジトリの根から書かれていなくてもよい。**

    CLAUDE.md は `app/lib/` の中身を `core/itinerary.dart` と書くことがあり、
    読み手にはそれで正しい。根からの相対でないというだけで「実在しない」と
    言うと、26 件のうち 26 件が誤検出になって、誰も読まなくなる。
    """
    bare = ref.rstrip("/")
    if os.path.exists(os.path.join(root, bare)):
        return True
    if "*" in ref or "?" in ref:
        if globlib.glob(os.path.join(root, ref), recursive=True):
            return True
        return any(fnmatch.fnmatch(p, "*/" + bare) or fnmatch.fnmatch(p, bare)
                   for p in index)
    return any(p == bare or p.endswith("/" + bare) for p in index)


def _is_copied(rel_path):
    """そのまま写した規約か。中の例示はこのリポジトリのパスではない。"""
    return any(rel_path == "%s/%s/SKILL.md" % (SKILL_DIR, n) for n in COPIED_SKILLS)


def broken_refs(root, files):
    """(参照元, 指している先) の一覧。リポジトリのどこにも無いものだけ。"""
    index, out = _repo_index(root), []
    for rel_path in files:
        if _is_copied(rel_path):
            continue
        text = _read(os.path.join(root, rel_path))
        if not text:
            continue
        for ref in sorted(_candidate_refs(text)):
            if ref in _ON_DEMAND:
                continue
            if not _exists(root, ref, index):
                out.append((rel_path, ref))
    return out


def unknown_commands(root, files, known_plugins):
    """指している /plugin:command のうち、当てが無いもの。

    入っているプラグインの一覧は取れないので、体制ファイルが前提として
    挙げているものだけを既知とする。当てが無い = 入れ忘れか、書き間違い。
    """
    known = set(known_plugins or []) | {"keeper"}
    out = []
    for rel_path in files:
        for plugin, cmd in _SLASH_CMD.findall(_read(os.path.join(root, rel_path))):
            if plugin not in known:
                out.append((rel_path, "/%s:%s" % (plugin, cmd)))
    return sorted(set(out))


def unfilled(root, files):
    """雛形の穴 ({{...}}) が埋まっていないもの。

    役の雛形をそのまま置くと、読んだ Claude が「{{想定利用者}}」の立場で
    ふるまおうとする。埋め忘れは、静かに役を壊す。
    """
    out = []
    for rel_path in files:
        for hole in sorted(set(_HOLE.findall(_read(os.path.join(root, rel_path))))):
            out.append((rel_path, "{{%s}}" % hole))
    return out


def doc_files(root, inv):
    """参照を照合する対象。CLAUDE.md と .claude/ 配下の md。"""
    files = list(inv["agents"]) + list(inv["commands"]) + list(inv["skills"])
    if inv["claude_md"]:
        files.insert(0, inv["claude_md"])
    return files


# ------------------------------------------------------------------ 役とのずれ

# 生成したプロジェクトが keeper 無しで回るために要るもの。
# ここが欠けると、役が読む規約や日々の入口がプラグイン側にしか無い状態になる。
REQUIRED_SKILLS = ("flat-view", "claude-md", "docs-style", "code-comments")
REQUIRED_COMMANDS = ("standup", "critique", "ship", "docs", "code", "routine")
# 役がいるときだけ要るコマンド
ROLE_COMMANDS = {"marketer": "market"}

def placed_gap(role_names, inv):
    """(足りない skill, 足りない command)。役に応じて要るものも見る。"""
    have_s = {os.path.basename(os.path.dirname(p)) for p in inv["skills"]}
    have_c = {os.path.splitext(os.path.basename(p))[0] for p in inv["commands"]}
    want_c = set(REQUIRED_COMMANDS)
    for role, cmd in ROLE_COMMANDS.items():
        if role in (role_names or []):
            want_c.add(cmd)
    return sorted(set(REQUIRED_SKILLS) - have_s), sorted(want_c - have_c)


def copied_drift(root, plugin_root):
    """写した規約が、写し元と違っていないか。plugin_root が無ければ見ない。"""
    if not plugin_root:
        return []
    out = []
    for name in COPIED_SKILLS:
        src = os.path.join(plugin_root, "templates", "skills", name, "SKILL.md")
        dst = os.path.join(root, SKILL_DIR, name, "SKILL.md")
        if not os.path.isfile(src) or not os.path.isfile(dst):
            continue
        if _read(src) != _read(dst):
            out.append(name)
    return out


def role_gap(role_names, inv):
    """(体制にあるのに置かれていない役, 置かれているのに体制に無い agent)。"""
    placed = {os.path.splitext(os.path.basename(p))[0] for p in inv["agents"]}
    wanted = set(role_names or [])
    return sorted(wanted - placed), sorted(placed - wanted)


# ------------------------------------------------- 生成したときの姿 (指紋)

MANIFEST = ".claude/manifest.json"

SKIP_DIRS = {
    ".git", "node_modules", "build", ".dart_tool", "Pods", "vendor",
    ".venv", "venv", "__pycache__", ".next", "dist", ".gradle", "target",
    ".idea", ".vscode", "coverage", "DerivedData",
}

# 依存を宣言するファイル。中身が変わればプロジェクトの土台が変わったとみなす
DEP_FILES = (
    "package.json", "pubspec.yaml", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json", "build.gradle",
    "build.gradle.kts", "Package.swift",
)

SOURCE_EXTS = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".dart": "dart",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".swift": "swift", ".cs": "csharp", ".php": "php", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".scala": "scala",
    ".ipynb": "notebook",
}

# 規模がこれだけ動いたら「別のプロジェクトになった」と言ってよい
GROWTH = 0.4


def file_digest(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()[:8]
    except Exception:
        return None


# ------------------------------------------------------------------- 指紋を取る

def take(root):
    """いまのリポジトリの姿。走査は 1 回で済ませる。"""
    langs, files, top_dirs = {}, 0, []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if name in SKIP_DIRS or name.startswith("."):
            continue
        if os.path.isdir(os.path.join(root, name)):
            top_dirs.append(name)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            lang = SOURCE_EXTS.get(ext)
            if not lang:
                continue
            files += 1
            langs[lang] = langs.get(lang, 0) + 1
    deps = {}
    for name in DEP_FILES:
        full = os.path.join(root, name)
        if os.path.isfile(full):
            deps[name] = file_digest(full)
    return {
        "langs": sorted(k for k, v in langs.items() if v >= 3) or sorted(langs),
        "top_dirs": top_dirs,
        "files": files,
        "deps": deps,
    }


def compare(was, now):
    """指紋の差を人が読める形で。差が無ければ空リスト。"""
    if not isinstance(was, dict) or not was:
        return []
    out = []

    gone = [d for d in was.get("top_dirs") or [] if d not in (now.get("top_dirs") or [])]
    added = [d for d in now.get("top_dirs") or [] if d not in (was.get("top_dirs") or [])]
    if added:
        out.append("最上位に %s が増えた" % " ".join(added))
    if gone:
        out.append("最上位から %s が消えた" % " ".join(gone))

    was_langs, now_langs = set(was.get("langs") or []), set(now.get("langs") or [])
    if now_langs - was_langs:
        out.append("言語が増えた (%s)" % " ".join(sorted(now_langs - was_langs)))
    if was_langs - now_langs:
        out.append("言語が消えた (%s)" % " ".join(sorted(was_langs - now_langs)))

    old_n, new_n = was.get("files") or 0, now.get("files") or 0
    if old_n and abs(new_n - old_n) > old_n * GROWTH:
        out.append("ソースが %d → %d ファイル" % (old_n, new_n))

    was_deps, now_deps = was.get("deps") or {}, now.get("deps") or {}
    changed = sorted(k for k in now_deps if k in was_deps and now_deps[k] != was_deps[k])
    new_deps = sorted(k for k in now_deps if k not in was_deps)
    if changed:
        out.append("依存の定義が変わった (%s)" % " ".join(changed))
    if new_deps:
        out.append("依存の定義が増えた (%s)" % " ".join(new_deps))
    return out


# ------------------------------------------------------------------- 台帳 (json)

def manifest_path(root):
    return os.path.join(root, MANIFEST)


def load_manifest(root):
    try:
        with open(manifest_path(root), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_manifest(root, data):
    full = manifest_path(root)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    tmp = full + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, full)
    return full


def stamp(root, paths, at):
    """生成したファイルの指紋を控える。あとで手が入ったかを見るため。"""
    data = load_manifest(root)
    gen = data.get("generated")
    if not isinstance(gen, dict):
        gen = {}
    for rel_path in paths:
        d = file_digest(os.path.join(root, rel_path))
        if d:
            gen[rel_path] = d
    data["version"] = 1
    data["at"] = at
    data["generated"] = gen
    data["fingerprint"] = take(root)
    return save_manifest(root, data)


def edited_by_hand(root):
    """生成したときと中身が違うもの。作り直す前に、必ずここを見る。"""
    gen = (load_manifest(root) or {}).get("generated") or {}
    out = []
    for rel_path, was in sorted(gen.items()):
        full = os.path.join(root, rel_path)
        if not os.path.exists(full):
            out.append((rel_path, "消えている"))
            continue
        if file_digest(full) != was:
            out.append((rel_path, "手が入っている"))
    return out


def drift(root):
    """(差の一覧, 前回の日付)。控えが無ければ空。"""
    data = load_manifest(root)
    was = data.get("fingerprint")
    if not was:
        return [], None
    return compare(was, take(root)), data.get("at")
