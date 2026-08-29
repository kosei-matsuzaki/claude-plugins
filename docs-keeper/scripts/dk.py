#!/usr/bin/env python3
"""docs-keeper の実行本体。フックからも、スラッシュコマンドからも呼ばれる。

  track        PostToolUse。このセッションで触ったファイルを控える
  stop-report  Stop。docs に未反映らしいものがあれば一度だけ指摘する(止めない)
  guard        PreToolUse(Write)。規約にない置き場所への新規 md を差し戻す
  check        現状の診断を人が読める形で出す(--since <ref> で差分の起点を指定)
  session      直近のセッションが触ったファイルを出す

どれも失敗したらだまって諦める。ドキュメントの都合でセッションを壊さない。
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import policy as P  # noqa: E402

SKIP_DIRS = {
    ".git", "node_modules", "build", ".dart_tool", "Pods", "vendor",
    ".venv", "venv", "__pycache__", ".next", "dist", ".gradle", "target",
}


# ------------------------------------------------------------------ utilities

def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def state_path(session_id):
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-docs-keeper")
    os.makedirs(base, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return os.path.join(base, safe + ".json")


def load_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"edits": {}, "reported": []}


def sweep_old_state(days=7):
    """置きっぱなしの記録を片づける。失敗しても構わない。"""
    import time
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-docs-keeper")
    cutoff = time.time() - days * 86400
    try:
        for name in os.listdir(base):
            full = os.path.join(base, name)
            if os.path.getmtime(full) < cutoff:
                os.remove(full)
    except Exception:
        pass


def save_state(session_id, state):
    try:
        tmp = state_path(session_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, state_path(session_id))
    except Exception:
        pass


def rel(root, path):
    try:
        return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
    except Exception:
        return None


def git(root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def changed_paths(root, since=None):
    if since:
        raw = git(root, "diff", "--name-only", since)
        return {p for p in raw.splitlines() if p}
    raw = git(root, "status", "--porcelain")
    out = set()
    for line in raw.splitlines():
        if len(line) > 3:
            out.add(line[3:].split(" -> ")[-1].strip().strip('"'))
    return out


def line_count(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


DOC_EXTS = (".md", ".ipynb")


def all_docs(root, exts=DOC_EXTS):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.lower().endswith(tuple(exts)):
                r = rel(root, os.path.join(dirpath, name))
                if r and not r.startswith(".."):
                    found.append(r)
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
    return line_count(path), "行"


def archive_globs(policy):
    d = P.opt(policy, "archive.dir")
    if not isinstance(d, str) or not d:
        return []
    return [d if d.endswith("/") else d + "/"]


def in_archive(policy, relpath):
    globs = archive_globs(policy)
    return bool(globs) and P.matches_any(relpath, globs)


def index_targets(root, index_rel):
    """索引が指している先。markdown リンクと、素の path 記述の両方を拾う。"""
    path = os.path.join(root, index_rel or "")
    if not index_rel or not os.path.isfile(path):
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
        joined = os.path.normpath(os.path.join(base, href)).replace(os.sep, "/")
        targets.add(joined)
    return targets, text


# ---------------------------------------------------------------------- track

def cmd_track():
    data = read_hook_input()
    inp = data.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("notebook_path")
    if not path:
        return 0
    root, _, _ = P.load(data.get("cwd") or os.getcwd())
    r = rel(root, path)
    if not r or r.startswith(".."):
        return 0
    session = data.get("session_id") or ""
    state = load_state(session)
    state.setdefault("edits", {})
    state["edits"][r] = state["edits"].get(r, 0) + 1
    state["root"] = root
    if state["edits"][r] == 1 and len(state["edits"]) == 1:
        sweep_old_state()          # セッションの最初の書き込みのときだけ
    save_state(session, state)
    return 0


# ---------------------------------------------------------------- stop-report

def cmd_stop_report():
    data = read_hook_input()
    session = data.get("session_id") or ""
    state = load_state(session)
    edits = state.get("edits") or {}
    if not edits:
        return 0

    root = state.get("root") or data.get("cwd") or os.getcwd()
    root, ppath, pol = P.load(root)
    touched = list(edits)

    if not ppath:
        # 規約がまだ無いリポジトリ。一度だけ声をかけて、あとは黙る。
        if "nopolicy" in state.get("reported", []) or len(touched) < 5:
            return 0
        if not any(t.lower().endswith(".md") for t in touched) and not os.path.isdir(
            os.path.join(root, "docs")
        ):
            return 0
        state.setdefault("reported", []).append("nopolicy")
        save_state(session, state)
        emit("docs-keeper: このリポジトリにはまだ規約 (docs/.docs-policy.yml) がありません。"
             "`/docs-keeper:init` で現状から作れます。")
        return 0

    if pol and pol.get("_error"):
        if "broken" not in state.get("reported", []):
            state.setdefault("reported", []).append("broken")
            save_state(session, state)
            emit("docs-keeper: %s を読めませんでした (%s)。書式を直してください。"
                 % (rel(root, ppath), pol["_error"]))
        return 0

    if not P.opt(pol, "notify.enabled", True):
        return 0
    min_edits = P.opt(pol, "notify.min_source_edits", 1) or 1

    dirty = changed_paths(root)
    reported = set(state.get("reported", []))
    findings = []

    # 1. 触った実装に対して、対応する docs が動いていない
    for i, rule in enumerate(P.watch_rules(pol)):
        key = "watch:%d" % i
        if key in reported:
            continue
        hits = [t for t in touched if P.matches_any(t, rule["source"])]
        if len(hits) < min_edits:
            continue
        if any(P.matches_any(t, rule["docs"]) for t in touched):
            continue
        # 別セッションで書きかけならそれを尊重する
        if any(P.matches_any(d, rule["docs"]) for d in dirty):
            continue
        where = " / ".join(rule["docs"])
        why = ("(%s)" % rule["why"]) if rule["why"] else ""
        findings.append("・%s を変更 %s → %s が未更新" % (short(hits), why, where))
        reported.add(key)

    # 2. 索引に載っていない新しい md を作った
    idx = P.opt(pol, "index")
    res = index_targets(root, idx)
    if res:
        targets, text = res
        for t in touched:
            key = "orphan:" + t
            if key in reported or not t.lower().endswith(DOC_EXTS) or t == idx:
                continue
            if not P.matches_any(t, [d for d, _ in P.layout_paths(pol)] or ["docs/**"]):
                continue
            if t in targets or t in text or os.path.basename(t) in text:
                continue
            findings.append("・%s が索引 %s に載っていない" % (t, idx))
            reported.add(key)

    # 3. 上限を超えて伸びた
    for t in touched:
        key = "limit:" + t
        if key in reported or not t.lower().endswith(DOC_EXTS):
            continue
        archived = in_archive(pol, t)
        cap = None
        if archived and t.lower().endswith(".md"):
            cap = P.opt(pol, "archive.rotate.max_lines")
        if not isinstance(cap, int):
            cap = P.limit_for(pol, t)
        if not isinstance(cap, int):
            continue
        n, unit = doc_size(root, t)
        if n > cap:
            # archive にあるものに「archive 送り」は勧めない。割るほうを勧める。
            advice = "割りどき" if archived else "archive 送りか圧縮どき"
            findings.append("・%s が %d %s (上限 %d)。%s" % (t, n, unit, cap, advice))
            reported.add(key)

    if not findings:
        return 0

    state["reported"] = sorted(reported)
    save_state(session, state)
    emit("docs-keeper: docs が追いついていないかもしれません\n"
         + "\n".join(findings)
         + "\n→ `/docs-keeper:sync` で反映、`/docs-keeper:check` で全体を確認できます。")
    return 0


def short(paths, limit=2):
    if len(paths) <= limit:
        return " ".join(paths)
    return "%s ほか %d 件" % (" ".join(paths[:limit]), len(paths) - limit)


def emit(message):
    json.dump({"systemMessage": message}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------- guard

def cmd_guard():
    data = read_hook_input()
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or not path.lower().endswith(DOC_EXTS):
        return 0
    if os.path.exists(path):          # 既存ファイルの書き換えには口を出さない
        return 0
    root, ppath, pol = P.load(data.get("cwd") or os.getcwd())
    if not ppath or (pol or {}).get("_error"):
        return 0
    if not P.opt(pol, "guard.enabled", True):
        return 0
    # 見張る拡張子。notebook は既定では見ない(生成物として作られることがあるため)
    exts = P.opt(pol, "guard.extensions", [".md"])
    if not path.lower().endswith(tuple(e.lower() for e in exts)):
        return 0
    r = rel(root, path)
    if not r or r.startswith(".."):   # リポジトリの外は関知しない
        return 0
    allowed = [d for d, _ in P.layout_paths(pol)] + list(P.opt(pol, "guard.allow", []) or [])
    if not allowed or P.matches_any(r, allowed):
        return 0
    # 規約が守備範囲としていない場所 (アプリのソース内 README など) は素通し
    scope = P.opt(pol, "guard.scope", ["docs/**", "*.md"])
    if not P.matches_any(r, scope):
        return 0
    lines = ["docs-keeper: %s は規約にない置き場所です。" % r, "", "決めてある置き場所:"]
    for d, role in P.layout_paths(pol):
        lines.append("  %-28s %s" % (d, role))
    lines += [
        "",
        "どれかに寄せるか、本当に新しい区分なら %s の layout に足してから書いてください。"
        % rel(root, ppath),
        "(索引 %s への追記も忘れずに)" % (P.opt(pol, "index") or "docs/README.md"),
    ]
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


# ---------------------------------------------------------------------- check

def cmd_check(argv):
    since = None
    start = os.getcwd()
    for i, a in enumerate(argv):
        if a == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
        elif a == "--root" and i + 1 < len(argv):
            start = argv[i + 1]
    root, ppath, pol = P.load(start)
    out = ["# docs-keeper check", "root: %s" % root]

    if not ppath:
        out.append("policy: なし → `/docs-keeper:init` で作る")
        pol = {}
    elif (pol or {}).get("_error"):
        out.append("policy: %s (読めない: %s)" % (rel(root, ppath), pol["_error"]))
        pol = {}
    else:
        out.append("policy: %s" % rel(root, ppath))

    mds = all_docs(root)
    out.append("")
    out.append("## ドキュメント一覧 (%d 件)" % len(mds))
    for m in mds:
        n, unit = doc_size(root, m)
        archived = in_archive(pol, m)
        cap = None
        if archived and m.lower().endswith(".md"):
            cap = P.opt(pol, "archive.rotate.max_lines")
        if not isinstance(cap, int):
            cap = P.limit_for(pol, m)
        flag = ""
        if isinstance(cap, int) and n > cap:
            flag = "  ← 上限 %d %s" % (cap, "超過。割りどき" if archived else "超過")
        out.append("  %5d%-3s %s%s" % (n, unit, m, flag))

    idx = P.opt(pol, "index")
    res = index_targets(root, idx) if idx else None
    if res:
        targets, text = res
        orphans = [
            m for m in mds
            if m != idx and m.startswith(os.path.dirname(idx) + "/")
            and m not in targets and m not in text
            and os.path.basename(m) not in text
        ]
        out.append("")
        out.append("## 索引 (%s) に載っていない md: %d 件" % (idx, len(orphans)))
        out += ["  " + o for o in orphans] or ["  なし"]
        missing = sorted(
            t for t in targets
            if t.lower().endswith(DOC_EXTS) and not os.path.exists(os.path.join(root, t))
        )
        if missing:
            out.append("")
            out.append("## 索引が指しているのに存在しない: %d 件" % len(missing))
            out += ["  " + m for m in missing]

    layout = P.layout_paths(pol)
    if layout:
        scope = P.opt(pol, "guard.scope", ["docs/**"])
        stray = [
            m for m in mds
            if P.matches_any(m, scope) and not P.matches_any(m, [d for d, _ in layout])
        ]
        out.append("")
        out.append("## 規約にない置き場所: %d 件" % len(stray))
        out += ["  " + s for s in stray] or ["  なし"]

    globs = archive_globs(pol)
    if globs:
        arc = [m for m in mds if in_archive(pol, m)]
        total = sum(doc_size(root, m)[0] for m in arc if m.lower().endswith(".md"))
        cap = P.opt(pol, "archive.rotate.max_lines")
        by = P.opt(pol, "archive.rotate.by", "none")
        out.append("")
        out.append("## 記録 (%s) %d 件 / 合計 %d 行 / 分け方: %s"
                   % (globs[0], len(arc), total, by))
        for m in arc:
            n, unit = doc_size(root, m)
            arc_cap = cap if m.lower().endswith(".md") else None
            flag = "  ← 割りどき" if isinstance(arc_cap, int) and n > arc_cap else ""
            out.append("  %5d%-3s %s%s" % (n, unit, m, flag))
        aidx = P.opt(pol, "archive.index")
        if aidx:
            res2 = index_targets(root, aidx)
            if not res2:
                out.append("  記録の索引 %s が無い。作ると引けるようになる" % aidx)
            else:
                t2, text2 = res2
                miss = [m for m in arc if m != aidx and m not in t2
                        and os.path.basename(m) not in text2]
                out.append("  記録の索引 %s に載っていない: %s"
                           % (aidx, ("%d 件 → %s" % (len(miss), " ".join(miss))) if miss else "なし"))

    rules = P.watch_rules(pol)
    if rules:
        changed = changed_paths(root, since)
        label = ("%s からの差分" % since) if since else "未コミットの差分"
        out.append("")
        out.append("## 変更に対して docs が動いていないもの (%s)" % label)
        hit = False
        for rule in rules:
            src = sorted(c for c in changed if P.matches_any(c, rule["source"]))
            if not src:
                continue
            if any(P.matches_any(c, rule["docs"]) for c in changed):
                continue
            hit = True
            out.append("  %s → %s が未更新 %s"
                       % (short(src, 3), " / ".join(rule["docs"]),
                          ("(%s)" % rule["why"]) if rule["why"] else ""))
        if not hit:
            out.append("  なし")

    sys.stdout.write("\n".join(out) + "\n")
    return 0


# -------------------------------------------------------------------- session

def cmd_session(argv):
    """このリポジトリで直近に動いていたセッションが触ったファイルを出す。"""
    start = os.getcwd()
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            start = argv[i + 1]
    root, _, _ = P.load(start)
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-docs-keeper")
    best, best_mtime = None, -1
    for name in os.listdir(base) if os.path.isdir(base) else []:
        if not name.endswith(".json"):
            continue
        full = os.path.join(base, name)
        try:
            with open(full, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if data.get("root") != root:
            continue
        mtime = os.path.getmtime(full)
        if mtime > best_mtime:
            best, best_mtime = data, mtime
    if not best or not best.get("edits"):
        sys.stdout.write("このセッションで触ったファイルの記録はありません。git の差分を使ってください。\n")
        return 0
    edits = best["edits"]
    sys.stdout.write("# このセッションで触ったファイル (%d 件)\n" % len(edits))
    for path, count in sorted(edits.items(), key=lambda kv: -kv[1]):
        sys.stdout.write("  %3d回  %s\n" % (count, path))
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "track":
            return cmd_track()
        if cmd == "stop-report":
            return cmd_stop_report()
        if cmd == "guard":
            return cmd_guard()
        if cmd == "check":
            return cmd_check(sys.argv[2:])
        if cmd == "session":
            return cmd_session(sys.argv[2:])
    except Exception as exc:
        if cmd == "check":
            sys.stdout.write("docs-keeper check に失敗: %s\n" % exc)
        return 0
    sys.stderr.write(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
