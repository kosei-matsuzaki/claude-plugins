#!/usr/bin/env python3
"""claude-keeper の実行本体。フックからも、スラッシュコマンドからも呼ばれる。

  check    docs / コード / .claude/ をまとめて診断する
  measure  いまの実測を出す (規約の上限を決めるときに使う)
  drift    生成したときからのずれだけを出す
  brief    SessionStart。ずれと手直しを一度だけ知らせる (止めない)
  guard    PreToolUse(Write)。規約にない置き場所への新規ファイルを差し戻す
  stamp    生成したファイルの指紋を控える (init / refresh が呼ぶ)
  judge    「いまは直さない」判断を台帳に書く

どれも失敗したらだまって諦める。規約の都合でセッションを壊さない。
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import policy as P    # noqa: E402
import ledger as Ld   # noqa: E402
import crew as C      # noqa: E402
import docs as D      # noqa: E402
import report as R    # noqa: E402
import scan as S      # noqa: E402

STATE_DIR = "claude-keeper"
MAX_ROWS = 12


# ------------------------------------------------------------------ utilities

def read_hook_input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def state_path(session_id):
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), STATE_DIR)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "none") + ".json")


def load_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"reported": []}


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
        r = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
        return None if r.startswith("..") else r
    except Exception:
        return None


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", root] + list(args),
                             capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def changed_paths(root, since=None):
    if since:
        return {p for p in git(root, "diff", "--name-only", since).splitlines() if p}
    out = set()
    for line in git(root, "status", "--porcelain", "-uall").splitlines():
        if len(line) > 3:
            out.add(line[3:].split(" -> ")[-1].strip().strip('"'))
    return out


def emit(message, context=None):
    out = {"systemMessage": message}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "SessionStart",
                                     "additionalContext": context}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


class Sifter(object):
    """台帳と突き合わせながら節を組み立てる。黙らせたものは数えて後で出す。"""

    def __init__(self, entries, pol):
        self.entries, self.pol = entries, pol
        self.hidden, self.problems = [], 0

    def section(self, title, records):
        keep, hidden = Ld.sift(records, self.entries, self.pol)
        self.hidden += hidden
        self.problems += len(keep)
        rows = ["  " + r["text"] for r in keep[:MAX_ROWS]]
        if len(keep) > MAX_ROWS:
            rows.append("  ... ほか %d 件" % (len(keep) - MAX_ROWS))
        return ["", "## %s: %d 件" % (title, len(keep))] + (rows or ["  なし"])


# --------------------------------------------------------------- 領域ごとの節

def docs_sections(root, pol, sifter, since):
    sub = pol.get("docs") or {}
    if not sub:
        return ["", "## docs: 規約が無い。`/claude-keeper:init` で作れる"]
    found = D.all_docs(root)
    orphans, missing = D.orphan_findings(root, sub, found)
    out = ["", "## 文書 %d 件" % len(found)]
    out += sifter.section("長すぎる文書", D.size_findings(root, sub, found))
    out += sifter.section("索引から辿れない", orphans)
    if missing:
        out += sifter.section("索引が指しているのに存在しない", missing)
    out += sifter.section("規約にない置き場所", D.stray_findings(sub, found))
    out += sifter.section("規約にあるが実在しない置き場所", D.layout_findings(root, sub))
    out += sifter.section("同じ話が複数の文書にある", D.overlap_findings(root, sub, found))
    out += sifter.section("同じ文が複数の文書にある (二重管理)",
                          D.duplicate_findings(root, sub, found))
    out += sifter.section("CLAUDE.md の伸びた節 (docs へ出す候補)", D.section_findings(root, sub))
    out += sifter.section("変更に対して文書が動いていない",
                          D.watch_findings(sub, changed_paths(root, since)))
    return out


def code_sections(root, pol, sifter, since):
    sub = pol.get("code") or {}
    if not sub:
        return ["", "## コード: 規約が無い。`/claude-keeper:init` で作れる"]
    files = S.source_files(root, sub)
    data = R.collect(root, sub, files)
    targets = sorted(data)
    if since:
        changed = changed_paths(root, since)
        targets = [t for t in targets if t in changed]
    out = ["", "## コード %d ファイル / %d 行"
           % (len(data), sum(i["total"] for i in data.values()))]
    out += sifter.section("長すぎるもの", R.size_findings(sub, data, targets))
    if P.layers(pol):
        bad, homeless = R.layer_findings(sub, data, targets)
        out += sifter.section("層の逸脱", bad)
        out += sifter.section("どの層にも属していない", homeless)
        out += sifter.section("膨らんだディレクトリ", R.dir_findings(sub, data))
    else:
        out += ["", "## 層: 決めていない。`/code` が実物から提案できる"]
    out += sifter.section("行がそのまま重なっているコード", R.dup_findings(sub, data, targets))
    out += sifter.section("形が似ている関数 (共通化できるかは読んで決める)",
                          R.similar_findings(sub, data, targets))
    dead, syms = R.dead_findings(sub, data)
    out += sifter.section("どこからも import されていない", dead)
    if syms:
        out += sifter.section("定義だけで呼ばれていない (候補)", syms)
    out += sifter.section("コメント", R.comment_findings(sub, data, targets))
    return out


def crew_records(root, pol):
    """.claude/ が腐っていないか。参照切れ・埋め残し・指紋のずれ・手直し。"""
    out, inv = [], C.scan(root)
    files = C.doc_files(root, inv)
    for src, ref in C.broken_refs(root, files):
        out.append(R.rec(src, "ref:" + ref,
                         "%s が %s を指しているが、実在しない" % (src, ref), "/claude-keeper:refresh"))
    for src, hole in C.unfilled(root, files):
        out.append(R.rec(src, "hole:%s:%s" % (src, hole),
                         "%s の雛形が埋まっていない (%s)" % (src, hole), "/claude-keeper:refresh"))
    for src, cmd in C.unknown_commands(root, files, ["claude-keeper"]):
        out.append(R.rec(src, "cmd:" + cmd,
                         "%s が %s を勧めているが、当てが無い" % (src, cmd), "/claude-keeper:refresh"))
    diffs, was_at = C.drift(root)
    for d in diffs:
        out.append(R.rec("", "drift:" + d.split(" ")[0],
                         "土台が変わった: %s (前回 %s)" % (d, was_at or "不明"), "/claude-keeper:refresh"))
    return out, inv


def crew_sections(root, pol, sifter):
    records, inv = crew_records(root, pol)
    out = ["", "## 置かれているもの",
           "  CLAUDE.md      %s" % ("%d 行" % inv["claude_md_lines"] if inv["claude_md"] else "無い"),
           "  agents         %d  %s" % (len(inv["agents"]), " ".join(_stems(inv["agents"]))),
           "  commands       %d  %s" % (len(inv["commands"]), " ".join(_stems(inv["commands"]))),
           "  skills         %d  %s" % (len(inv["skills"]), " ".join(_skill_names(inv["skills"])))]
    for src, event, n in C.hook_events(root):
        out.append("  hooks          %s %s x%d" % (src, event, n))
    roles = P.roles(pol)
    if roles:
        missing, extra = C.role_gap(P.role_names(pol), inv)
        out += ["", "## 体制 (%d 役)" % len(roles)]
        for role in roles:
            mark = "  ← 置かれていない" if role["name"] in missing else ""
            out.append("  %-14s %s%s" % (role["name"], role.get("why") or "", mark))
        if extra:
            out.append("  体制に無い agent: %s" % " ".join(extra))
    lack_s, lack_c = C.placed_gap(P.role_names(pol), inv)
    drifted = C.copied_drift(root, os.environ.get("CLAUDE_PLUGIN_ROOT"))
    hand = C.edited_by_hand(root)
    if lack_s or lack_c or drifted:
        out += ["", "## 自立していないところ"]
        if lack_s:
            out.append("  規約が写されていない: %s" % " ".join(lack_s))
        if lack_c:
            out.append("  コマンドが置かれていない: %s" % " ".join("/" + c for c in lack_c))
        if drifted:
            out.append("  写した規約が写し元と違う: %s  ← 古いか、手が入っている" % " ".join(drifted))
    if hand:
        out += ["", "## 生成物に手が入ったもの: %d 件" % len(hand)]
        out += ["  %-44s %s" % (p, how) for p, how in hand]
    out += sifter.section("生成物の腐り", records)
    return out


def _stems(paths):
    return [os.path.splitext(os.path.basename(p))[0] for p in paths]


def _skill_names(paths):
    return [os.path.basename(os.path.dirname(p)) for p in paths]


# ---------------------------------------------------------------------- check

def cmd_check(argv):
    """診断だけ。書き込みは一切しない。"""
    start, since, strict, show_judged = os.getcwd(), None, False, False
    only = []
    for i, a in enumerate(argv):
        if a == "--root" and i + 1 < len(argv):
            start = argv[i + 1]
        elif a == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
        elif a == "--only" and i + 1 < len(argv):
            only = argv[i + 1].split(",")
        elif a == "--strict":
            strict = True
        elif a == "--show-judged":
            show_judged = True
    root, path, pol = P.load(start)
    out = ["# claude-keeper check", "root: %s" % root]
    if pol is None:
        out.append("policy: なし → `/claude-keeper:init` で作る")
        pol = {}
    elif pol.get("_error"):
        out.append("policy: 読めない (%s)" % pol["_error"])
        sys.stdout.write("\n".join(out) + "\n")
        return 0
    else:
        out.append("policy: %s" % (rel(root, path) if path else "統合前の規約から読んだ"))
        proj = P.opt(pol, "project", {}) or {}
        if proj:
            out.append("project: %s / %s / 収益 %s"
                       % (proj.get("name") or "名前なし", proj.get("kind") or "kind なし",
                          proj.get("revenue") or "none"))
    legacy = (pol or {}).get("_legacy") or []
    if legacy:
        out.append("統合前の規約を読んでいる: %s → `/claude-keeper:init` で 1 つにまとめられる"
                   % " ".join(legacy))

    sifter = Sifter(Ld.load(root), pol)
    if not only or "crew" in only:
        out += crew_sections(root, pol, sifter)
    if not only or "docs" in only:
        out += docs_sections(root, pol, sifter, since)
    if not only or "code" in only:
        out += code_sections(root, pol, sifter, since)

    if sifter.hidden:
        out += ["", "## 黙らせているもの: %d 件%s"
                % (len(sifter.hidden), "" if show_judged else "  (--show-judged で中身)")]
        if show_judged:
            for record, entry in sifter.hidden:
                out.append("  %s" % record["text"])
                out.append("      → 「%s」%s %s"
                           % (entry.get("decision"), entry.get("why") or "",
                              ("期限 " + entry["until"]) if entry.get("until") else ""))
    old = Ld.legacy_files(root)
    if old:
        out += ["", "## 統合前の台帳が残っている: %s" % " ".join(old)]
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if (strict and sifter.problems) else 0


# -------------------------------------------------------------------- measure

def cmd_measure(argv):
    """いまの実測。規約の上限を決めるときに使う。**最大値に合わせない。**"""
    start = argv[argv.index("--root") + 1] if "--root" in argv else os.getcwd()
    root, _, pol = P.load(start)
    pol = pol or {}
    out = ["# claude-keeper measure", "root: %s" % root, ""]

    sub = pol.get("code") or {}
    files = S.source_files(root, sub)
    if files:
        data = R.collect(root, sub, files)
        funcs = [f for i in data.values() for f in i["funcs"]]
        rows = [("ファイル行数", sorted(i["total"] for i in data.values())),
                ("関数行数", sorted(f["lines"] for f in funcs)),
                ("入れ子の段数", sorted(f["depth"] for f in funcs)),
                ("引数の数", sorted(f["params"] for f in funcs if "params" in f))]
        out.append("%-22s %6s %6s %6s %8s" % ("", "中央", "90%", "最大", "提案"))
        for label, vals in rows:
            if vals:
                out.append("%-22s %6d %6d %6d %8d"
                           % (label, _pct(vals, 50), _pct(vals, 90), vals[-1],
                              _round_up(_pct(vals, 90))))
        ratios = sorted(i["comment"] / float(i["code"]) for i in data.values() if i["code"])
        if ratios:
            out.append("%-22s %5.0f%% %5.0f%% %5.0f%%   %.2f-%.2f"
                       % ("コメント比率", _pct(ratios, 50) * 100, _pct(ratios, 90) * 100,
                          ratios[-1] * 100, max(0.02, _pct(ratios, 10)), _pct(ratios, 90) * 1.2))
        out.append("")

    found = D.all_docs(root)
    if found:
        sizes = sorted(D.doc_size(root, m)[0] for m in found if m.lower().endswith(".md"))
        if sizes:
            out.append("%-22s %6d %6d %6d %8d"
                       % ("文書の行数", _pct(sizes, 50), _pct(sizes, 90), sizes[-1],
                          _round_up(_pct(sizes, 90))))
    out.append("")
    out.append("**提案は 90% 点の切り上げ。**最大値に合わせると、上限は何も捕まえない。")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


def _pct(sorted_vals, p):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p / 100))]


def _round_up(n):
    if n <= 10:
        return int(n) + 1
    step = 10 if n < 100 else (50 if n < 500 else 100)
    return int((n + step - 1) // step * step)


# ------------------------------------------------------------- drift / stamp

def cmd_drift(argv):
    start = argv[argv.index("--root") + 1] if "--root" in argv else os.getcwd()
    root, _, _ = P.load(start)
    diffs, was_at = C.drift(root)
    hand = C.edited_by_hand(root)
    if not diffs and not hand:
        sys.stdout.write("生成したとき (%s) からのずれはありません。\n" % (was_at or "不明"))
        return 0
    sys.stdout.write("# ずれ (前回 %s)\n" % (was_at or "不明"))
    for d in diffs:
        sys.stdout.write("  " + d + "\n")
    for path, how in hand:
        sys.stdout.write("  %s に %s\n" % (path, how))
    return 0


def cmd_stamp(argv):
    """生成したファイルを控える。ここを呼ばないと「手が入った」が分からなくなる。"""
    start, paths, i = os.getcwd(), [], 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            start, i = argv[i + 1], i + 2
            continue
        paths.append(argv[i])
        i += 1
    root, _, _ = P.load(start)
    rels = []
    for p in paths:
        r = rel(root, p) if os.path.isabs(p) else p.replace(os.sep, "/")
        if r and os.path.isfile(os.path.join(root, r)):
            rels.append(r)
        else:
            sys.stdout.write("見つからないので控えません: %s\n" % p)
    full = C.stamp(root, rels, time.strftime("%Y-%m-%d"))
    sys.stdout.write("%d 件を %s に控えました。\n" % (len(rels), rel(root, full)))
    return 0


# ---------------------------------------------------------------------- judge

def cmd_judge(argv):
    args, i = {}, 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            args[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    if not args.get("key") or not args.get("why"):
        sys.stdout.write("--key と --why は必ず要ります (理由の無い判断は次に読む人が覆せない)。\n")
        return 1
    root, _, _ = P.load(args.get("root") or os.getcwd())
    entry = {"key": args["key"], "path": args.get("path") or "",
             "decision": args.get("decision") or "いまは直さない", "why": args["why"],
             "until": args.get("until") or "", "date": time.strftime("%Y-%m-%d"),
             "by": args.get("by") or ""}
    if args.get("at", "").lstrip("-").isdigit():
        entry["at"] = int(args["at"])
    full = Ld.append(root, entry)
    sys.stdout.write("台帳に書きました: %s (%s)\n" % (rel(root, full), entry["key"]))
    return 0


# ---------------------------------------------------------------------- brief

def cmd_brief():
    """セッションの頭に一度だけ。生成したときからずれていないかだけを見る。"""
    data = read_hook_input()
    root, path, pol = P.load(data.get("cwd") or os.getcwd())
    session = data.get("session_id") or ""
    state = load_state(session)
    if "brief" in state.get("reported", []):
        return 0
    state.setdefault("reported", []).append("brief")
    save_state(session, state)

    if pol is None:
        return 0                                   # 規約が無いリポジトリでは黙る
    if pol.get("_error"):
        emit("claude-keeper: 規約を読めませんでした (%s)。書式を直してください。" % pol["_error"])
        return 0
    if not P.opt(pol, "notify.enabled", True) or not P.opt(pol, "notify.drift", True):
        return 0

    lines = []
    diffs, was_at = C.drift(root)
    hand = C.edited_by_hand(root)
    if diffs:
        lines += ["・" + d for d in diffs[:4]]
    if hand:
        lines.append("・生成物に手が入っている: %s" % " ".join(p for p, _ in hand[:3]))
    if pol.get("_legacy"):
        lines.append("・統合前の規約を読んでいる (%s)。`/claude-keeper:init` で 1 つにまとめられる"
                     % " ".join(pol["_legacy"]))
    if not lines:
        return 0
    text = ("claude-keeper: 組んだ %s から、土台が動いています\n" % (was_at or "とき")
            + "\n".join(lines)
            + "\n→ 組み直すなら `/claude-keeper:refresh`、いまの姿を見るなら `/claude-keeper:check`。")
    emit(text, context=text)
    return 0


# ---------------------------------------------------------------------- guard

def cmd_guard():
    """規約にない置き場所への新規ファイルを差し戻す。**既存の書き換えには口を出さない。**"""
    data = read_hook_input()
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or os.path.exists(path):
        return 0
    root, _, pol = P.load(data.get("cwd") or os.getcwd())
    if not pol or pol.get("_error"):
        return 0
    r = rel(root, path)
    if not r:
        return 0

    if r.lower().endswith(tuple(P.opt(pol, "docs.guard.extensions", [".md"]) or [".md"])):
        if not P.opt(pol, "docs.guard.enabled", True):
            return 0
        allowed = [d for d, _ in P.layout_paths(pol)] + list(P.opt(pol, "docs.guard.allow", []) or [])
        scope = P.opt(pol, "docs.guard.scope", ["docs/**", "*.md"])
        if allowed and P.matches_any(r, scope) and not P.matches_any(r, allowed):
            lines = ["claude-keeper: %s は規約にない置き場所です。" % r, "", "決めてある置き場所:"]
            lines += ["  %-28s %s" % (d, role) for d, role in P.layout_paths(pol)]
            lines += ["", "どれかに寄せるか、本当に新しい区分なら .claude/policy.yml の "
                          "docs.layout に足してから書いてください。"]
            sys.stderr.write("\n".join(lines) + "\n")
            return 2
        return 0

    layers = P.layers(pol)
    if not layers or not P.opt(pol, "code.guard.enabled", True):
        return 0
    inc, exc = S.scope_patterns(pol.get("code") or {})
    if not P.matches_any(r, inc) or P.matches_any(r, exc):
        return 0
    if any(P.matches_any(r, layer["path"]) for layer in layers):
        return 0
    lines = ["claude-keeper: %s はどの層にも属していません。" % r, "", "決めてある層:"]
    lines += ["  %-14s %-28s %s" % (l["name"], " ".join(l["path"])[:28], l["role"])
              for l in layers]
    lines += ["", "どれかに寄せるか、本当に新しい層なら .claude/policy.yml の "
                  "code.layers に足してから書いてください。"]
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "check":
            return cmd_check(sys.argv[2:])
        if cmd == "measure":
            return cmd_measure(sys.argv[2:])
        if cmd == "drift":
            return cmd_drift(sys.argv[2:])
        if cmd == "stamp":
            return cmd_stamp(sys.argv[2:])
        if cmd == "judge":
            return cmd_judge(sys.argv[2:])
        if cmd == "brief":
            return cmd_brief()
        if cmd == "guard":
            return cmd_guard()
    except Exception as exc:
        if cmd in ("check", "measure", "drift", "stamp", "judge"):
            sys.stdout.write("claude-keeper %s に失敗: %s\n" % (cmd, exc))
        return 0
    sys.stderr.write(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
