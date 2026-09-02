# claude-plugins

個人開発リポジトリで使う Claude Code プラグイン置き場。

```
/plugin marketplace add kosei-matsuzaki/claude-plugins
```

| プラグイン | 何をするか |
|---|---|
| [docs-keeper](docs-keeper/) | README / CLAUDE.md / `docs/` 配下の md を、最新・整頓・簡潔に保つ |
| [code-keeper](code-keeper/) | コードが伸びる・散る・崩れる・残るのを見張る。機械が候補を出し、Claude が読んで判断し、判断を台帳に残す |

## 手元で直すとき

```bash
/plugin marketplace add ~/university/artifacts/claude-plugins
```

ローカルパスで登録しておくと、編集がそのまま反映される。
GitHub 版と両方入れると衝突するので、どちらか片方にする。
