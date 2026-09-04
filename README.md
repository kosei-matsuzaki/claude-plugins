# claude-plugins

個人開発リポジトリで使う Claude Code プラグイン置き場。

```
/plugin marketplace add kosei-matsuzaki/claude-plugins
/plugin install keeper@kosei-plugins
```

| プラグイン | 何をするか |
|---|---|
| [keeper](keeper/) | リポジトリに Claude を導入する入口。現状を測って規約を作り、そのプロジェクトに要る役・規約・コマンドを `.claude/` に生成する |

**生成したあと、プロジェクトは keeper が入っていなくても回る。**役が読む規約も
日々のコマンドもプロジェクトに置くので、リポジトリを他所へ持っていっても壊れない。

```
/keeper:init      現状を測って規約を作り、.claude/ を生成する
/keeper:check     docs・コード・.claude/ をまとめて診断する (書き換えない)
/keeper:refresh   生成したときからずれたぶんだけ組み直す
```

以降はプロジェクト側に生成された `/standup` `/docs` `/code` `/ship` `/critique`
`/routine`(と、収益を求めるなら `/market`)を使う。

## 手元で直すとき

```bash
/plugin marketplace add ~/university/artifacts/claude-plugins
```

ローカルパスで登録しておくと、編集がそのまま反映される。
GitHub 版と両方入れると衝突するので、どちらか片方にする。

## 統合前から使っていたリポジトリ

`docs-keeper` と `code-keeper` は keeper に統合した(2026-09-04)。
**規約ファイルはそのまま読める** — `docs/.docs-policy.yml` と `.code-policy.yml` が
残っていれば `docs:` / `code:` として扱い、判断台帳も引き継ぐ。
`/keeper:init` が `.claude/policy.yml` 1 つへの移行を提案する
(**値は 1 つも変えない**)。
