"""言語ごとの見かた。拡張子から、コメント記号・関数の探し方・import の書式を引く。

構文解析はしない。行単位の走査で「だいたい合っている」ところまでをやる。
だから外れることがある。ck.py が出すのは常に「候補」で、消す判断は人に残す。

新しい言語を足すときは LANGS に 1 行足す。関数の見つけ方が特殊でなければ
GENERIC_FUNC (波かっこで囲む言語ぜんぶに効く) をそのまま使えばよい。
"""

import re

BRACE, INDENT, END = "brace", "indent", "end"

# 関数の宣言に見えて関数ではないもの。除かないと `if (x) {` を関数と数える。
_NOT = (r"(?!(?:if|for|while|switch|catch|do|else|return|new|typeof|await|yield|"
        r"match|when|using|lock|unless|elsif|foreach|with)\b)")

# 波かっこ言語の共通形。行末が `{` で終わる宣言だけを拾う。
# 引数の中の `{` は許す — `({ label, onPress }) => {` のような分割代入があるため。
GENERIC_FUNC = (r"^(?P<i>[\s}\)]*)(?:[\w@\[\]<>,\.\?\*&:\"]+\s+)*" + _NOT +
                r"(?P<n>\w+)\s*\([^;]*\)\s*[-\w:<>\[\],\?\s]*\{\s*$")

# JS/TS のアロー関数。`const f = async (a) => {`
ARROW_FUNC = (r"^(?P<i>\s*)(?:export\s+)?(?:const|let|var)\s+(?P<n>\w+)\s*(?::[^=]*)?=\s*"
              r"(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]*)?=>\s*\{\s*$")

_C_LINE, _C_BLOCK = ["//"], [("/*", "*/")]
_JS_IMPORT = [r"""from\s+['"]([^'"]+)['"]""",
              r"""require\(\s*['"]([^'"]+)['"]""",
              r"""^\s*import\s+['"]([^'"]+)['"]""",
              r"""import\(\s*['"]([^'"]+)['"]"""]


def _lang(name, style, line, block, func, imports, string='"\'', mstring=()):
    return {
        "name": name, "style": style, "line": line, "block": block,
        "func": [re.compile(p) for p in func],
        "imports": [re.compile(p) for p in imports],
        "string": string, "mstring": list(mstring),
    }


_PY = _lang(
    "python", INDENT, ["#"], [],
    [r"^(?P<i>\s*)(?:async\s+)?def\s+(?P<n>\w+)\s*\("],
    [r"^\s*from\s+([\w\.]+)\s+import", r"^\s*import\s+([\w\.]+)"],
    mstring=[('"""', '"""'), ("'''", "'''")],
)
_TS = _lang("typescript", BRACE, _C_LINE, _C_BLOCK, [GENERIC_FUNC, ARROW_FUNC], _JS_IMPORT,
            mstring=[("`", "`")])
_DART = _lang(
    "dart", BRACE, _C_LINE, _C_BLOCK, [GENERIC_FUNC],
    [r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]"""],
    mstring=[('"""', '"""'), ("'''", "'''")],
)
_GO = _lang(
    "go", BRACE, _C_LINE, _C_BLOCK,
    [r"^(?P<i>)func\s+(?:\([^)]*\)\s*)?(?P<n>\w+)"],
    [r"""^\s*(?:import\s+)?(?:_\s+|\.\s+|\w+\s+)?"([\w\./\-]+)"\s*$"""],
    mstring=[("`", "`")],
)
_RUST = _lang(
    "rust", BRACE, _C_LINE, _C_BLOCK,
    [r"^(?P<i>\s*)(?:pub(?:\([^)]*\))?\s+)?(?:default\s+|const\s+|async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*fn\s+(?P<n>\w+)"],
    [r"^\s*(?:pub\s+)?use\s+([\w:]+)", r"^\s*mod\s+(\w+)\s*;"],
)
_JAVA = _lang("java", BRACE, _C_LINE, _C_BLOCK, [GENERIC_FUNC],
              [r"^\s*import\s+(?:static\s+)?([\w\.\*]+)\s*;"])
_KOTLIN = _lang(
    "kotlin", BRACE, _C_LINE, _C_BLOCK,
    [r"^(?P<i>\s*)(?:\w+\s+)*fun\s+(?:<[^>]+>\s*)?(?:[\w\.<>]+\.)?(?P<n>\w+)\s*\(", GENERIC_FUNC],
    [r"^\s*import\s+([\w\.\*]+)"],
)
_SWIFT = _lang("swift", BRACE, _C_LINE, _C_BLOCK,
               [r"^(?P<i>\s*)(?:\w+\s+)*func\s+(?P<n>\w+)"],
               [r"^\s*(?:@testable\s+)?import\s+([\w\.]+)"])
_CS = _lang("csharp", BRACE, _C_LINE, _C_BLOCK, [GENERIC_FUNC],
            [r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?([\w\.]+)\s*;"])
_PHP = _lang(
    "php", BRACE, ["//", "#"], _C_BLOCK,
    [r"^(?P<i>\s*)(?:(?:public|private|protected|static|final|abstract)\s+)*function\s+(?P<n>\w+)\s*\("],
    [r"^\s*use\s+([\w\\\\]+)", r"""(?:require|include)(?:_once)?\s*\(?['"]([^'"]+)['"]"""],
)
_RUBY = _lang("ruby", END, ["#"], [("=begin", "=end")],
              [r"^(?P<i>\s*)def\s+(?P<n>[\w\.\?!=\[\]]+)"],
              [r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]"""])
_C = _lang("c", BRACE, _C_LINE, _C_BLOCK, [GENERIC_FUNC],
           [r"^\s*#\s*include\s+[\"<]([^\">]+)[\">]"])
_SCALA = _lang("scala", BRACE, _C_LINE, _C_BLOCK,
               [r"^(?P<i>\s*)(?:\w+\s+)*def\s+(?P<n>\w+)", GENERIC_FUNC],
               [r"^\s*import\s+([\w\.\_]+)"])

LANGS = {
    ".py": _PY, ".pyi": _PY,
    ".ts": _TS, ".tsx": _TS, ".js": _TS, ".jsx": _TS, ".mjs": _TS, ".cjs": _TS,
    ".vue": _TS, ".svelte": _TS,
    ".dart": _DART,
    ".go": _GO,
    ".rs": _RUST,
    ".java": _JAVA,
    ".kt": _KOTLIN, ".kts": _KOTLIN,
    ".swift": _SWIFT,
    ".cs": _CS,
    ".php": _PHP,
    ".rb": _RUBY,
    ".c": _C, ".h": _C, ".cc": _C, ".cpp": _C, ".hpp": _C, ".m": _C, ".mm": _C,
    ".scala": _SCALA,
}

EXTS = tuple(sorted(LANGS))


def spec_for(path):
    dot = path.rfind(".")
    return LANGS.get(path[dot:].lower()) if dot >= 0 else None


# --------------------------------------------------- コメントと文字列を落とす

def strip_line(text, spec, state):
    """1 行から、コードだけ・コメントがあったか・次の行へ持ち越す状態を返す。

    state は「いま閉じ待ちの記号」(ブロックコメントか複数行文字列)。
    文字列は消して落とす。同じ処理を重複検出でも使うので、
    リテラルだけが違うコピペは「同じ」と見なされる — 狙いどおり。
    """
    if state:
        end = text.find(state)
        if end < 0:
            return "", True, state
        return strip_line(text[end + len(state):], spec, None)[0], True, None

    out, i, n, had_comment = [], 0, len(text), False
    while i < n:
        ch = text[i]
        hit = False
        for tok in spec["line"]:
            if text.startswith(tok, i):
                return "".join(out), True, None
        for open_tok, close_tok in spec["block"] + spec["mstring"]:
            if text.startswith(open_tok, i):
                end = text.find(close_tok, i + len(open_tok))
                if end < 0:
                    return "".join(out), True, close_tok
                i = end + len(close_tok)
                had_comment = True
                hit = True
                break
        if hit:
            continue
        if ch in spec["string"]:
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == ch:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return "".join(out), had_comment, None


def classify(text, spec):
    """1 ファイルを行ごとに (種別, コード部分) へ。種別は code / comment / blank。"""
    rows, state = [], None
    for raw in text.splitlines():
        code, had_comment, state2 = strip_line(raw, spec, state)
        inside = state is not None
        state = state2
        if code.strip():
            rows.append(("code", code))
        elif had_comment or inside:
            rows.append(("comment", ""))
        elif raw.strip():
            rows.append(("code", raw))   # 判定できないものはコードとして数える
        else:
            rows.append(("blank", ""))
    return rows
