#!/usr/bin/env python3
"""code-keeper の実行本体。フックからも、スラッシュコマンドからも呼ばれる。

  track        PostToolUse。このセッションで触ったファイルを控える
  stop-report  Stop。触ったコードが崩れかけていれば一度だけ言う(止めない)
  guard        PreToolUse(Write)。層のどこにも属さない場所への新規ファイルを差し戻す
  check        現状の診断を人が読める形で出す
  judge        Claude が下した判断を台帳に書く (同じ指摘を繰り返さないため)
  measure      いまの実物を測る。規約の上限を決めるときに使う
  session      直近のセッションが触ったファイルを出す

どれも失敗したらだまって諦める。整理の都合でセッションを壊さない。
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lang as L      # noqa: E402
import ledger as Ld   # noqa: E402
import policy as P    # noqa: E402
import report as R    # noqa: E402
import scan as S      # noqa: E402

DEEP_SCAN_MAX = 1200      # これを超えるファイル数では、停止時の重い調べものをしない


# ------------------------------------------------------------------ utilities

def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def state_dir():
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-code-keeper")
    os.makedirs(base, exist_ok=True)
    return base


def state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return os.path.join(state_dir(), safe + ".json")


def load_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"edits": {}, "reported": []}


def save_state(session_id, state):
    try:
        tmp = state_path(session_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, state_path(session_id))
    except Exception:
        pass


def sweep_old_state(days=7):
    import time
    cutoff = time.time() - days * 86400
    try:
        for name in os.listdir(state_dir()):
            full = os.path.join(state_dir(), name)
            if os.path.getmtime(full) < cutoff:
                os.remove(full)
    except Exception:
        pass


def rel(root, path):
    try:
        r = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
        return None if r.startswith("..") else r
    except Exception:
        return None


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", root] + list(args),
                             capture_output=True, text=True, timeout=15)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def changed_paths(root, since=None):
    if since:
        raw = git(root, "diff", "--name-only", since)
        return {p for p in raw.splitlines() if p}
    out = set()
    for line in git(root, "status", "--porcelain").splitlines():
        if len(line) > 3:
            out.add(line[3:].split(" -> ")[-1].strip().strip('"'))
    return out


def emit(message):
    json.dump({"systemMessage": message}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------- track

def cmd_track():
    data = read_hook_input()
    inp = data.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("notebook_path")
    if not path or not path.lower().endswith(L.EXTS):
        return 0
    root, _, _ = P.load(data.get("cwd") or os.getcwd())
    r = rel(root, path)
    if not r:
        return 0
    session = data.get("session_id") or ""
    state = load_state(session)
    state.setdefault("edits", {})
    state["edits"][r] = state["edits"].get(r, 0) + 1
    state["root"] = root
    if len(state["edits"]) == 1 and state["edits"][r] == 1:
        sweep_old_state()
    save_state(session, state)
    return 0


# ---------------------------------------------------------------- stop-report

def _first_words(session, state, loaded, touched):
    """規約が無い / 壊れているときの一言。どちらも一度だけ言って、あとは黙る。"""
    root, ppath, pol = loaded
    if not ppath:
        if "nopolicy" in state.get("reported", []) or len(touched) < 8:
            return True
        state.setdefault("reported", []).append("nopolicy")
        save_state(session, state)
        emit("code-keeper: このリポジトリにはまだ規約 (.code-policy.yml) がありません。"
             "`/code-keeper:init` で現状から作れます。")
        return True
    if pol and pol.get("_error"):
        if "broken" not in state.get("reported", []):
            state.setdefault("reported", []).append("broken")
            save_state(session, state)
            emit("code-keeper: %s を読めませんでした (%s)。書式を直してください。"
                 % (rel(root, ppath), pol["_error"]))
        return True
    return not P.opt(pol, "notify.enabled", True)


def _stop_records(pol, data, targets, deep):
    """触ったファイルに関わる指摘だけを集める。

    重い調べもの (層・重なり・デッドコード) は deep のときだけ。
    停止時に時間をかけない。
    """
    out = R.size_findings(pol, data, targets)
    out += [r for r in R.comment_findings(pol, data, targets)
            if r["kind"] in ("commented_out", "undocumented", "comment_thin")]
    if not deep:
        return out

    bad, homeless = R.layer_findings(pol, data, targets)
    out += bad[:3] + homeless[:2]
    out += [r for r in R.dir_findings(pol, data)
            if any(os.path.dirname(t) == r["path"] for t in targets)]
    out += R.dup_findings(pol, data, targets)[:3]
    out += R.similar_findings(pol, data, targets)[:3]
    dead, _ = R.dead_findings(pol, data)
    out += [r for r in dead if r["path"] in set(targets)][:2]
    return out


def cmd_stop_report():
    """セッションの終わりに一度だけ言う。止めない。触ったファイルのことだけ言う。"""
    hook = read_hook_input()
    session = hook.get("session_id") or ""
    state = load_state(session)
    edits = state.get("edits") or {}
    if not edits:
        return 0

    loaded = P.load(state.get("root") or hook.get("cwd") or os.getcwd())
    root, _, pol = loaded
    touched = sorted(edits)
    if _first_words(session, state, loaded, touched):
        return 0

    files = S.source_files(root, pol)
    targets = [t for t in touched if t in set(files)]
    if not targets:
        return 0

    reported = set(state.get("reported", []))
    deep = len(files) <= DEEP_SCAN_MAX
    data = R.collect(root, pol, files if deep else targets)
    # 判断済みのものは言わない。台帳が無ければ何も変わらない。
    records, _ = Ld.sift(_stop_records(pol, data, targets, deep), Ld.load(root), pol)

    findings = []
    for record in records:
        key = "%s|%s" % (record["path"], record["key"])
        if key in reported:      # 同じ指摘はセッション中に繰り返さない
            continue
        reported.add(key)
        findings.append("・%s → `/code-keeper:%s`" % (record["text"], record["cmd"]))

    if not findings:
        return 0

    state["reported"] = sorted(reported)
    save_state(session, state)
    emit("code-keeper: 触ったコードが読みにくくなりかけています\n"
         + "\n".join(findings[:5])
         + "\n→ 中身を読んで判断するなら `/code-keeper:review`、全体を見るなら `/code-keeper:check`。")
    return 0


# ---------------------------------------------------------------------- guard

def cmd_guard():
    hook = read_hook_input()
    path = (hook.get("tool_input") or {}).get("file_path")
    if not path or not path.lower().endswith(L.EXTS):
        return 0
    if os.path.exists(path):          # 既存ファイルの書き換えには口を出さない
        return 0
    root, ppath, pol = P.load(hook.get("cwd") or os.getcwd())
    if not ppath or (pol or {}).get("_error") or not P.opt(pol, "guard.enabled", True):
        return 0
    layers = P.layers(pol)
    if not layers:
        return 0
    r = rel(root, path)
    if not r:
        return 0
    exts = P.as_list(P.opt(pol, "guard.extensions"))
    if exts and not r.lower().endswith(tuple(e.lower() for e in exts)):
        return 0
    inc, exc = S.scope_patterns(pol)
    if (inc and not P.matches_any(r, inc)) or P.matches_any(r, exc):
        return 0
    if P.matches_any(r, P.as_list(P.opt(pol, "guard.allow"))):
        return 0
    if S.layer_of(r, layers):
        return 0

    lines = ["code-keeper: %s は、決めてある層のどこにも入っていません。" % r, "", "層:"]
    for layer in layers:
        lines.append("  %-14s %-24s %s"
                     % (layer["name"], " ".join(layer["path"])[:24], layer["role"]))
    same = [f for f in S.source_files(root, pol)
            if os.path.basename(f) == os.path.basename(r)]
    if same:
        lines += ["", "同じ名前のファイルが既にあります。分けるより足すほうが良くないか:"]
        lines += ["  " + s for s in same[:5]]
    lines += [
        "",
        "どれかの層に置くか、本当に新しい層なら %s の layers に足してから書いてください。"
        % rel(root, ppath),
    ]
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


# ---------------------------------------------------------------------- check

SECTIONS = ("size", "layers", "dupes", "dead", "comments")


def _check_args(argv):
    opts = {"since": None, "root": os.getcwd(), "only": list(SECTIONS),
            "strict": False, "top": 12, "show_judged": False}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--since", "--root", "--only", "--top") and i + 1 < len(argv):
            val = argv[i + 1]
            if arg == "--only":
                opts["only"] = [x for x in val.split(",") if x in SECTIONS]
            elif arg == "--top":
                opts["top"] = int(val)
            else:
                opts[arg[2:]] = val
            i += 1
        elif arg == "--strict":
            opts["strict"] = True
        elif arg == "--show-judged":
            opts["show_judged"] = True
        i += 1
    return opts


def _rows(items, top):
    """一覧の体裁。ゼロなら「なし」、多すぎるなら「ほか N 件」で畳む。"""
    if not items:
        return ["  なし"]
    out = list(items[:top])
    if len(items) > top:
        out.append("  ほか %d 件" % (len(items) - top))
    return out


class Sifter(object):
    """台帳と突き合わせながら節を組み立てる。黙らせたものは数えて後で出す。"""

    def __init__(self, entries, pol, top):
        self.entries, self.pol, self.top = entries, pol, top
        self.hidden, self.problems = [], 0

    def section(self, title, records):
        keep, hidden = Ld.sift(records, self.entries, self.pol)
        self.hidden += hidden
        self.problems += len(keep)
        return ["", "## %s: %d 件" % (title, len(keep))] + \
               _rows(["  " + r["text"] for r in keep], self.top)


def _sections(pol, data, targets, scoped, sifter):
    """区分ごとの見出しと中身。順番は「いま効くもの」から。"""
    out = {}
    out["size"] = sifter.section("長すぎるもの", R.size_findings(pol, data, targets))

    if not P.layers(pol):
        out["layers"] = ["", "## 層: 決めていない (layers が空)。"
                             "`/code-keeper:review` が実物から提案できる"]
    else:
        bad, homeless = R.layer_findings(pol, data, scoped)
        out["layers"] = (sifter.section("層の逸脱", bad)
                         + sifter.section("どの層にも属していない", homeless)
                         + sifter.section("膨らんだディレクトリ", R.dir_findings(pol, data)))

    dups = R.dup_findings(pol, data, scoped)
    out["dupes"] = (sifter.section("行がそのまま重なっているコード", dups)
                    + sifter.section("形が似ている関数 (共通化できるかは読んで決める)",
                                     R.similar_findings(pol, data, scoped)))

    dead, syms = R.dead_findings(pol, data)
    out["dead"] = sifter.section("どこからも import されていない", dead)
    if syms:
        out["dead"] += sifter.section("定義だけで呼ばれていない (候補)", syms)

    out["comments"] = sifter.section("コメント", R.comment_findings(pol, data, targets))
    return out


def cmd_check(argv):
    """診断を人が読める形で出す。書き込みは一切しない。"""
    opts = _check_args(argv)
    root, ppath, pol = P.load(opts["root"])
    out = ["# code-keeper check", "root: %s" % root]
    if not ppath:
        out.append("policy: なし → `/code-keeper:init` で作る (いまは既定値で見ている)")
        pol = {}
    elif (pol or {}).get("_error"):
        out.append("policy: %s (読めない: %s)" % (rel(root, ppath), pol["_error"]))
        pol = {}
    else:
        out.append("policy: %s" % rel(root, ppath))

    data = R.collect(root, pol, S.source_files(root, pol))
    inc = S.scope_patterns(pol)[0]
    out.append("対象: %d ファイル / %d 行%s"
               % (len(data), sum(info["total"] for info in data.values()),
                  (" (scope: %s)" % " ".join(inc)) if inc else ""))
    if not data:
        out += ["", "見るファイルがありません。scope.include を確かめてください。"]
        sys.stdout.write("\n".join(out) + "\n")
        return 0

    targets = sorted(data)
    if opts["since"]:
        changed = changed_paths(root, opts["since"])
        targets = [t for t in targets if t in changed]
        out.append("差分: %s から変わった %d ファイルだけを見る" % (opts["since"], len(targets)))
    # --since のときは、差分に関わるものだけに絞る (リポジトリ全体を蒸し返さない)
    scoped = targets if opts["since"] else None

    sifter = Sifter(Ld.load(root), pol, opts["top"])
    sections = _sections(pol, data, targets, scoped, sifter)
    for name in opts["only"]:
        out += sections.get(name, [])

    if sifter.hidden:
        out += ["", "## 判断済みとして黙らせているもの: %d 件" % len(sifter.hidden)]
        if opts["show_judged"]:
            for record, entry in sifter.hidden:
                out.append("  %s" % record["text"])
                out.append("    → %s (%s、%s)" % (entry.get("decision"), entry.get("why"),
                                                  entry.get("date")))
        else:
            out.append("  %s で中身を見る。台帳: %s"
                       % ("--show-judged", Ld.LEDGER))

    sys.stdout.write("\n".join(out) + "\n")
    return 1 if (opts["strict"] and sifter.problems) else 0


# ---------------------------------------------------------------------- judge

def cmd_judge(argv):
    """Claude が下した判断を台帳に書く。コマンド側から呼ばれる。"""
    opts, i = {"root": os.getcwd()}, 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 1
        i += 1
    if not opts.get("path") or not opts.get("key"):
        sys.stdout.write("使い方: judge --path <ファイル> --key <指摘の鍵> "
                         "--decision <どうすると決めたか> --why <理由> [--at <そのときの数>]\n"
                         "鍵は check の出力にあるもの (file_lines / similar:_delete:7 など)。\n")
        return 1
    root, _, _ = P.load(opts["root"])
    entry = {"path": opts["path"], "key": opts["key"],
             "decision": opts.get("decision"), "why": opts.get("why"),
             "by": opts.get("by")}
    if opts.get("at", "").isdigit():
        entry["at"] = int(opts["at"])
    where = Ld.append(root, entry)
    sys.stdout.write("台帳に書いた: %s\n  %s / %s → %s\n"
                     % (rel(root, where), entry["path"], entry["key"], entry["decision"]))
    return 0


# -------------------------------------------------------------------- measure

def pct(values, q):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * q), len(ordered) - 1)]


def pad(label, width):
    """全角を 2 で数えて幅をそろえる。%-16s だと日本語の列がずれる。"""
    used = sum(2 if ord(ch) > 0x2E80 else 1 for ch in label)
    return label + " " * max(width - used, 0)


def roundup(num, step):
    return int((num + step - 1) // step * step)


def cmd_measure(argv):
    """いまの実物を測る。規約の上限を「決める」のではなく「合わせる」ために使う。"""
    start = os.getcwd()
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            start = argv[i + 1]
    root, _, pol = P.load(start)
    pol = {} if not pol or pol.get("_error") else pol
    data = R.collect(root, pol, S.source_files(root, pol))
    if not data:
        sys.stdout.write("見るファイルがありません。scope.include を確かめてください。\n")
        return 0

    files = [info["total"] for info in data.values()]
    funcs = [fn["lines"] for info in data.values() for fn in info["funcs"]]
    depth = [fn["depth"] for info in data.values() for fn in info["funcs"]]
    params = [fn["params"] for info in data.values() for fn in info["funcs"]]
    ratio = [info["comment"] / float(info["code"] or 1)
             for info in data.values() if info["code"] >= 40]
    dirs = {}
    for rel_path in data:
        dirs[os.path.dirname(rel_path)] = dirs.get(os.path.dirname(rel_path), 0) + 1
    exts = {}
    for rel_path in data:
        ext = rel_path[rel_path.rfind("."):]
        exts[ext] = exts.get(ext, 0) + 1

    out = ["# code-keeper measure", "root: %s" % root,
           "対象: %d ファイル / %d 行" % (len(data), sum(files)), "",
           "拡張子: " + " ".join("%s×%d" % (e, n) for e, n in
                                 sorted(exts.items(), key=lambda kv: -kv[1])), "",
           pad("", 20) + "".join(" " * max(8 - sum(2 if ord(c) > 0x2E80 else 1 for c in h), 0) + h
                                 for h in ("中央", "90%", "最大", "提案")),
           "%s %7d %7d %7d %7d" % (pad("ファイル行数", 20), pct(files, .5), pct(files, .9),
                                   max(files), roundup(pct(files, .9) * 1.2, 50)),
           "%s %7d %7d %7d %7d" % (pad("関数行数", 20), pct(funcs, .5), pct(funcs, .9),
                                   max(funcs or [0]), roundup(pct(funcs, .9) * 1.2, 10)),
           "%s %7d %7d %7d %7d" % (pad("入れ子の深さ", 20), pct(depth, .5), pct(depth, .9),
                                   max(depth or [0]), max(pct(depth, .9) + 1, 4)),
           "%s %7d %7d %7d %7d" % (pad("引数の数", 20), pct(params, .5), pct(params, .9),
                                   max(params or [0]), max(pct(params, .9) + 1, 4)),
           "%s %7d %7d %7d %7d" % (pad("1 dir のファイル数", 20), pct(list(dirs.values()), .5),
                                   pct(list(dirs.values()), .9), max(dirs.values()),
                                   roundup(pct(list(dirs.values()), .9) * 1.3, 5)),
           "%s %6.0f%% %6.0f%% %6.0f%%  %.2f-%.2f"
           % (pad("コメント比率", 20), pct(ratio, .5) * 100, pct(ratio, .9) * 100,
              max(ratio or [0]) * 100, max(round(pct(ratio, .1), 2), 0.01),
              min(round(pct(ratio, .9) + 0.1, 2), 0.7)),
           "",
           "長いほうから 5 件:"]
    for rel_path in sorted(data, key=lambda r: -data[r]["total"])[:5]:
        out.append("  %5d行  %s" % (data[rel_path]["total"], rel_path))
    out += ["", "提案はいまの 90% 点をもとにした値。ここから始めて、下げていく。",
            "いちばん長い 1 本に上限を合わせない (1 本のために全体が緩くなる)。"]
    sys.stdout.write("\n".join(out) + "\n")
    return 0


# -------------------------------------------------------------------- session

def cmd_session(argv):
    start = os.getcwd()
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            start = argv[i + 1]
    root, _, _ = P.load(start)
    best, best_mtime = None, -1
    base = state_dir()
    for name in os.listdir(base) if os.path.isdir(base) else []:
        if not name.endswith(".json"):
            continue
        full = os.path.join(base, name)
        try:
            with open(full, encoding="utf-8") as fh:
                info = json.load(fh)
        except Exception:
            continue
        if info.get("root") != root:
            continue
        if os.path.getmtime(full) > best_mtime:
            best, best_mtime = info, os.path.getmtime(full)
    if not best or not best.get("edits"):
        sys.stdout.write("このセッションで触ったファイルの記録はありません。git の差分を使ってください。\n")
        return 0
    sys.stdout.write("# このセッションで触ったファイル (%d 件)\n" % len(best["edits"]))
    for path, count in sorted(best["edits"].items(), key=lambda kv: -kv[1]):
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
        if cmd == "judge":
            return cmd_judge(sys.argv[2:])
        if cmd == "measure":
            return cmd_measure(sys.argv[2:])
        if cmd == "session":
            return cmd_session(sys.argv[2:])
    except Exception as exc:
        if cmd == "check":
            sys.stdout.write("code-keeper check に失敗: %s\n" % exc)
        return 0
    sys.stderr.write(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
