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

| コマンド | 何をするか | 書き換える | 引数 |
|---|---|---|---|
| `init` | 現状から規約ファイルを作る | 規約ファイルだけ | `--force` |
| `check` | 診断する | **しない** | `--since <ref>` |
| `sync` | 実装の変更を docs に反映する | する(最小差分) | `--since <ref>` |
| `tidy` | 置き場所を規約に寄せ、索引を貼り直す | する(**承認を取ってから**) | — |
| `compact` | 冗長な docs を削り、記録を `archive/` へ送る | する | `[ファイル名]` |

`/docs-keeper:check` のように前置きを付けて呼ぶ。**迷ったら `check`。**
何も壊さずに、いま何が起きているかと、どのコマンドで解けるかを教えてくれる。

### 症状からコマンドを引く

| こうなっている | 使うもの |
|---|---|
| このリポジトリで初めて使う | `init` |
| 何が問題か知りたい / CI で見たい | `check` |
| 実装を直したが docs を直していない | `sync` |
| リリース前に、前の版からの積み残しを洗いたい | `check --since <前のタグ>` → `sync --since <同じ>` |
| `docs/` がフラットで、記録と仕様が混ざっている | `tidy` |
| 索引から辿れない md がある / リンクが切れている | `tidy` |
| 1 つのファイルが長い / 実装履歴が本文に混ざっている | `compact` |
| `archive/` が「割りどき」と言われた | `compact` |
| AI 臭い文章を直したい | `compact`(skill `docs-style` を当てる) |

停止時のフックは、この表を引かなくて済むように**どのコマンドを使うかまで言う**。

### 各コマンドの中身

**`init`** — 現状を診断し、リポジトリの性格に合う雛形を選んで `docs/.docs-policy.yml`
を書く。`layout` の `role` は既存の `docs/README.md` の説明文をそのまま使う
(勝手に言い換えない)。**既存の md は 1 つも動かさない。**
書く前に規約の全文と根拠を見せ、特に `watch` は 1 本ずつ確認する。
最後に、いま規約に反しているものの件数と、どのコマンドで解けるかを報告して終わる。
規約が既にあるときは止まって診断だけ返す(`--force` で作り直し)。

**`check`** — 書き込みを一切しない。いつも出るのは 5 つ:
ドキュメント一覧(md は行数、notebook はセル数)/ 索引から辿れないもの /
規約にない置き場所 / 記録の状態 / 変更に対して docs が動いていないもの。
「索引が指しているのに存在しないファイル」は、**あるときだけ**出る。
`--since <ref>` を渡すとその参照からの差分で最後の項目を見る。渡さなければ未コミットの差分。

**`sync`** — 「最新化して」を頼み忘れたぶんを埋める。
セッション中に触ったファイルと git 差分を集め、**変更の中身を実際に読んでから**書く
(ファイル名だけで docs を書き換えない)。**最小差分**で、周りの文章は整えない。
実装履歴は `archive/` にだけ書き、仕様書には結論だけ残す。
`TODO.md` の済んだ項目を `archive/` へ移し、索引も直す。
最後に**何を書かなかったか**とその理由を報告する。

**`tidy`** — 置き場所と索引を整える。中身の書き換えはしない。
索引から辿れない md・規約にない場所の md・リンク切れ・内容が重なっている md を拾い、
「移動 / 統合 / 削除 / 残す」の一覧を**先に出して承認を取ってから** `git mv` で動かす。
そのあと索引を書き直し、リンク切れを全部直し、規約の `layout` を実態に合わせる。

**`compact`** — 長さと文体を直す。skill `docs-style`(禁止事項リスト)がそのまま作業指示になる。
削る前に各段落を「残す / `archive/` へ移す / 消す」に仕分ける。
`archive/` 自身が「割りどき」と言われたときは、**中身を圧縮せず**期間か版で割って索引に 1 行足す。
報告は「420 行 → 180 行」の形で、**判断が微妙だったものを 2〜3 件挙げる**(戻せるように)。
引数にファイル名を渡すとそれだけ、渡さなければ上限を超えたものが対象。

### 使う順番

初回は `init` → `check` → (`tidy`) → (`compact`)。
以降は**フックに言われたときだけ** `sync` か `compact` を呼べばよい。
リリース前に `check --since <前のタグ>` を回すと積み残しが出る。

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
