# docs-keeper

README / CLAUDE.md / `docs/` 配下の md を、**最新・整頓・簡潔**に保つ。

解こうとしている 4 つの困りごと:

| 困りごと | 効くもの |
|---|---|
| 最新化を頼み忘れて、docs に反映されない事項が残る | Stop フックが停止時に指摘する |
| 新しい md が増えて docs が散らかる | Write フックが規約にない置き場所を差し戻す / `/docs-keeper:tidy` |
| 実装履歴が積もって docs が長くなる | 行数上限の指摘 / `/docs-keeper:compact` が `archive/` へ送る |
| その `archive/` が伸びすぎる | 索引 (`archive.index`) と期間・版での分割 (`archive.rotate`) |
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

### リポジトリの性格で雛形が変わる

| 雛形 | 向き |
|---|---|
| [default-policy.yml](skills/docs-policy/references/default-policy.yml) | アプリ・ライブラリ・道具。`release/` と `changelog.md` を持つ |
| [research-policy.yml](skills/docs-policy/references/research-policy.yml) | シミュレーション・機械学習・分析。`results.md` `reproduce.md` `experiments/` を持つ |

研究側の肝は **実験結果を `archive/` へ送らないこと**。実装履歴は結論さえ残れば
捨ててよいが、「この条件で回したらこうなった」は次と**比べる**ために残すもので、
archive に流すと比較対象を失う。表に生きたまま置き、archive へ送るのは
その系統を追うのをやめたときだけ。

規約は `docs/` という名前にも縛られない。`documentation/` を使っているなら
規約を `.claude/docs-policy.yml` に置いて `layout` をそちらに向ければ動く。

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
| 新しい md を書く前 | 規約 `layout` にない置き場所なら差し戻して、決めてある置き場所を示す(`guard.extensions` で notebook も対象にできる) |
| セッションが止まるとき | 未反映・索引漏れ・上限超過があれば**一度だけ**知らせる。止めはしない |

停止時の指摘はこう出る:

```
docs-keeper: docs が追いついていないかもしれません
・app/lib/core/scheduler/plan.dart を変更 (設計の核が動いた) → docs/architecture.md が未更新
・docs/TODO.md が 140 行 (上限 120)。archive 送りか圧縮どき
→ `/docs-keeper:sync` で反映、`/docs-keeper:check` で全体を確認できます。
```

**同じ指摘はセッション中に繰り返さない。** うるさくない代わりに、無視すれば残る。

## 記録 (`archive/`) の扱い

記録は**短く保つものではなく、引けるようにするもの**。1800 行の 1 ファイルは
grep できるかぎり困らない。困るのは「どこに何があるか分からない」ほう。

```yaml
archive:
  dir: docs/archive/
  index: docs/archive/README.md   # 索引に無い記録は、無いのと同じ
  rotate:
    by: year        # year(期間) / version(版) / none
    max_lines: 1500 # 超えたら「割りどき」と言う
```

archive にあるファイルには **「archive 送り」ではなく「割りどき」** と言う。
`/docs-keeper:compact` は `git mv` で期間か版に割り、索引に 1 行足す。
**中身は書き換えない** — 記録を圧縮すると後から引く意味が無くなる。

`max_lines` は行数なので notebook(セル数で数える)には当たらない。
notebook に上限をかけるなら `limits` にセル数で書く。

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
