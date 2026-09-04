---
name: policy
description: 規約ファイル .claude/policy.yml (体制・docs・コードを 1 つにまとめたもの) を作る・読む・直すときに使う。役の決め方、文書の置き場所と記録、層と依存の向き、上限の決め方、統合前の規約からの移行。/claude-keeper:init /claude-keeper:refresh の実行中と、規約を手で直すときに読む。
---

# 規約ファイル (.claude/policy.yml) の書きかた

置き場所は `.claude/policy.yml`。書式は YAML の狭い部分集合だけ — コメント /
`key: value` / 入れ子 / `- ` リスト / インラインリスト `[a, b]`。
**アンカーと複数行文字列は使えない。**

節は 3 つ。**それぞれ別の腐り方を見張る。**

| 節 | 見張るもの |
|---|---|
| `project` / `roles` / `generate` | 誰の目で見るか。生成したものが腐っていないか |
| `docs` | 文書が実装から離れる・散る・伸びる |
| `code` | コードが伸びる・散る・崩れる・残る |

## 雛形を選ぶ

| 雛形 | 選ぶ目安 |
|---|---|
| `templates/default-policy.yml` | 道具・ライブラリ。使うのは主に自分 |
| `templates/product-policy.yml` | **使う人がいて、収益を求める。**画面がある |
| `templates/research-policy.yml` | 回して結果を見る。実験・シミュレーション・分析 |

見分け方: `experiments/` `notebooks/` `configs/` や numpy・torch の類があれば
research。ストア・課金・利用者向けの README があれば product。**迷ったら聞く。**

**雛形は出発点で、正解ではない。**実測へ寄せる。

## 役 (roles)

**`why` が書けない役は置かない。**「あると良さそう」で置いた役は一度も呼ばれず、
`.claude/agents/` が読まれないファイルで埋まる。

```yaml
  - name: critic
    why: 作った本人しかいないので、機能の筋を疑う人がいない   # ○ 現に困っている
    why: 品質を高めるため                                     # × 何にでも書ける
```

**`stance` が役の中身。**ここが空だと、どの役も同じことを言い出す。

```yaml
stance: 開発者として                     # × 立場になっていない
stance: 半年後にこれを引き継ぐ人          # ○ 知らないことが決まる
stance: 出発前夜に片手で開いている人      # ○ 状況まである
```

基本の 4 役(`docs-auditor` / `code-steward` / `critic` / `reviewer`)に、
条件で `user-voice`(自分以外が使う)と `marketer`(`revenue` が `none`/`unknown` 以外)
を足す。**6 役を超えたら、たいてい 2 つは同じことを言っている。**

雛形は `templates/agents/`。**そのまま置かない** — `{{ }}` を埋め、`reads` を実在する
パスに差し替える。**穴は必ず 1 行に収める**(改行をまたぐと埋め残しの検出をすり抜ける)。

## docs

| 項目 | 何を決めるか |
|---|---|
| `index` | 全文書はここから辿れること。**索引に無い記録は、無いのと同じ** |
| `layout` | 置き場所と役割。ここに無い場所への新規文書は差し戻す |
| `limits` | パスごとの行数上限。超えたら指摘する |
| `watch` | 「ここを触ったらここを直す」の対応表 |
| `archive` | 記録の置き場・索引・分け方 |
| `guard` | 置き場所チェックの範囲と拡張子 |

**`watch` は 2〜3 本だけ。**作り方:

- 変わったら設計の説明が変わる中核 → `architecture.md`
- 画面 / API / CLI の入口 → `spec.md`
- バージョン・依存を定義するファイル → `changelog.md`
- `why` は「設計の核が動いた」のように、**読んだとき何を直せばいいか分かる**一言
- **迷ったものは入れない。鳴りすぎる規約は読まれなくなる**

### 記録 (archive) の扱い

記録は**短く保つものではなく、引けるようにするもの。**1800 行の 1 ファイルは
grep できるかぎり困らない。困るのは「どこに何があるか分からない」ほう。

```yaml
  archive:
    dir: docs/archive/
    index: docs/archive/README.md   # 索引に無い記録は、無いのと同じ
    rotate:
      by: year                      # year(期間) / version(版) / none
      max_lines: 1500               # 超えたら「割りどき」と言う
```

archive にあるものには**「archive 送り」ではなく「割りどき」**と言う。
割るのは `git mv` で期間か版に分け、索引に 1 行足すこと。**中身は書き換えない。**

**研究では実験結果を archive へ送らない。**「この条件で回したらこうなった」は
次と比べるためのもので、送ると比較対象を失う。

## code

| 項目 | 何を決めるか |
|---|---|
| `scope` | 見る範囲。**生成物は必ず `exclude` に入れる** |
| `layers` | 層と、依存してよい向き(`allow`)。`isolate` で横の呼び合いを止める |
| `limits` | `file_lines` / `function_lines` / `nesting` / `params` / `dir_files` |
| `comments` | 比率と連続量。**既定値は当てにならない。必ず測る** |
| `duplication` | `min_lines`(行の一致)/ `similar`(形の一致)/ `ignore` |
| `dead` | `entrypoints`(枠組みが名前で呼ぶもの)/ `symbols` |

層の切り方は [references/code-structure.md](references/code-structure.md)。**要点:**

- **層を決められないなら `layers` は空のままにする。**架空の層を書くと、
  実装が全部「逸脱」になって誰も見なくなる。`/code` が実物の import から提案できる
- **正しいアーキテクチャは 1 つではない。**規約のほうがずれていることもある

### 上限は測ってから決める

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" measure
```

**実測の 90% 点の切り上げから始める。最大値に合わせない**
(最大に合わせた上限は、何も捕まえない)。うるさければ下げるのではなく、
まず `exclude` から生成物が漏れていないかを疑う。

## うるさいと感じたら

順に: 台帳に書く(1 件ずつ、期限つきで)→ 上限を実測に合わせる →
**生成物が `code.scope.exclude` から漏れていないか** → `duplication.similar` を上げる →
`code.dead.entrypoints` を足す → `docs.watch` を減らす。
全部黙らせるなら `notify.enabled: false`。

## 統合前の規約からの移行

`docs/.docs-policy.yml` と `.code-policy.yml` があれば、そのまま読んで
`docs:` / `code:` として扱う。**中身は同じ形なので、移行は値を 1 つも変えずに
節へ移すだけ。**移したら旧ファイルを `git rm` し、台帳
(`.code-keeper/judgments.yml` / `.claude/crew-judgments.yml`)も
`.claude/judgments.yml` へ寄せる。

## 手で直したあと

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" check
```

役を足したのに agent を置いていなければ「置かれていない」と出る。
役を消したときは `.claude/agents/` の該当ファイルも消す。
