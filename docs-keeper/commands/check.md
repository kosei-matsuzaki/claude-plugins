---
description: docs の現状を診断する。書き換えはしない
allowed-tools: Bash, Read, Glob, Grep
argument-hint: "[--since <git-ref>]"
---

docs の現状を報告する。**ファイルは一切書き換えない。**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check $ARGUMENTS
```

`$ARGUMENTS` に `--since <ref>` があれば、その参照からの差分で
「実装が変わったのに docs が動いていないもの」を見る。無ければ未コミットの差分を見る。
リリース前の点検なら `--since` に前回のタグを渡すとよい。

出力をそのまま貼らず、次の形にまとめて報告する:

1. **いますぐ効くもの** — 未反映の docs、索引から辿れない md、存在しないファイルへのリンク
2. **溜まってきたもの** — 上限を超えたファイル、規約にない置き場所
3. **どのコマンドで解けるか** — `/docs-keeper:sync` / `:tidy` / `:compact` のどれか

件数がゼロの区分は「なし」の一行で済ませる。**問題が無いなら短く終わる。**
規約ファイル自体が無い場合は `/docs-keeper:init` を勧める。
