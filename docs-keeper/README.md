# docs-keeper

README / CLAUDE.md / `docs/` 配下の md を、**最新・整頓・簡潔**に保つ。

解こうとしている 4 つの困りごと:

| 困りごと | 効くもの |
|---|---|
| 最新化を頼み忘れて、docs に反映されない事項が残る | Stop フックが停止時に指摘する |
| 新しい md が増えて docs が散らかる | Write フックが規約にない置き場所を差し戻す / `/docs-keeper:tidy` |
| 実装履歴が積もって docs が長くなる | 行数上限の指摘 / `/docs-keeper:compact` が `archive/` へ送る |
| AI が書いた文章が読みにくい | skill `docs-style`(禁止事項リスト) |

## 使いかた

```
/plugin marketplace add kosei-matsuzaki/claude-plugins
/plugin install docs-keeper@kosei-plugins
```

リポジトリごとに一度だけ:

```
/docs-keeper:init
```

現状を診断して `docs/.docs-policy.yml` を作る。**既存の構成を書き起こすだけで、
勝手に並べ替えない。** 以降はフックがこの規約を見て動く。

## コマンド

| コマンド | 何をするか |
|---|---|
| `/docs-keeper:init` | 現状から規約ファイルを作る |
| `/docs-keeper:check` | 診断だけ。書き換えない。`--since <ref>` で起点を指定 |
| `/docs-keeper:sync` | 実装の変更を docs に反映する(最小差分) |
| `/docs-keeper:tidy` | 置き場所を規約に寄せ、索引を貼り直す |
| `/docs-keeper:compact` | 冗長な docs を削り、実装履歴を `archive/` へ送る |

## フック

| いつ | 何が起きるか |
|---|---|
| ファイルを書いたあと | 触ったパスを控える(`$TMPDIR/claude-docs-keeper/`。リポジトリは汚さない) |
| 新しい md を書く前 | 規約 `layout` にない置き場所なら差し戻して、決めてある置き場所を示す |
| セッションが止まるとき | 未反映・索引漏れ・上限超過があれば**一度だけ**知らせる。止めはしない |

停止時の指摘はこう出る:

```
docs-keeper: docs が追いついていないかもしれません
・app/lib/core/scheduler/plan.dart を変更 (設計の核が動いた) → docs/architecture.md が未更新
・docs/TODO.md が 140 行 (上限 120)。archive 送りか圧縮どき
→ `/docs-keeper:sync` で反映、`/docs-keeper:check` で全体を確認できます。
```

**同じ指摘はセッション中に繰り返さない。** うるさくない代わりに、無視すれば残る。

## 規約ファイル

`docs/.docs-policy.yml`。手で直してよい。全項目の意味は skill `docs-policy`、
雛形は [skills/docs-policy/references/default-policy.yml](skills/docs-policy/references/default-policy.yml)。

```yaml
index: docs/README.md          # 全 md はここから辿れること
layout:                        # 置き場所と役割。ここに無い場所への新規 md は差し戻す
  - path: docs/spec.md
    role: いまの仕様
limits:                        # 行数上限。超えたら指摘する
  docs/TODO.md: 120
  default: 400
watch:                         # 「ここを触ったらここを直す」の対応表
  - source: ["app/lib/core/**/*.dart"]
    docs: ["docs/architecture.md"]
    why: 設計の核が動いた
```

うるさいと感じたら、まず規約を疑う。`watch` を減らすか
`notify.min_source_edits` を上げる。全部黙らせるなら `notify.enabled: false`、
置き場所チェックだけ止めるなら `guard.enabled: false`。

## 前提

`python3`(macOS 標準の 3.9 で動く)と `git`。**追加のパッケージは要らない。**
規約ファイルは YAML の狭い部分集合だけを使い、同梱のパーサで読む。

フックが失敗しても、だまって諦めるだけでセッションは止まらない。
