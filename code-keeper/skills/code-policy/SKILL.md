---
name: code-policy
description: .code-policy.yml (code-keeper のコード規約ファイル) を作る・読む・直すときに使う。層と依存の向き、長さの上限、重複と使われていないコードの見つけ方をどう書くか。/code-keeper:init /code-keeper:relayout の実行中と、規約を手で直すときに読む。
---

# コード規約 (.code-policy.yml) の書きかた

置き場所は `.code-policy.yml`(リポジトリの根)。`.claude/code-policy.yml` でもよい。
書式は YAML の狭い部分集合だけ — コメント / `key: value` / 入れ子 / `- ` リスト /
インラインリスト `[a, b]`。**アンカーと複数行文字列は使えない。**

## 雛形を選ぶ

| 雛形 | 選ぶ目安 |
|---|---|
| `references/layered-policy.yml` | サーバ・CLI・業務ロジックの厚いもの。**規則を枠組みから離したい** |
| `references/feature-policy.yml` | 画面のあるもの (React / Next.js / Flutter)。**機能で切りたい** |
| `references/research-policy.yml` | 実験するもの。**回して結果を見る**のが主な仕事 |

見分け方: `experiments/` `notebooks/` `configs/` があるか、依存に numpy・torch・
pandas のたぐいが入っていれば research。`pages/` `components/` `features/` が
あれば feature。それ以外は layered。**迷ったら利用者に聞く。**

## 書くときの原則

**いまの姿を書き起こす。理想を書かない。** 規約は守れるから意味がある。
初日から全部が赤くなる規約は、次の日には誰も読まない。

1. **実在するディレクトリだけ `path` に書く。** 雛形にあって無いものは消す
2. **上限は実物を測ってから決める。** いちばん長いファイルの 1.2 倍を切り上げた値。
   そこから下げていく。いきなり理想値にすると、指摘が多すぎて全部無視される
3. **層は 3〜5 個。** 増やすと、どこに置くかで毎回迷う
4. **`allow` は狭く始める。** 逸脱が出たら、直すか、規約を緩めるかをその都度決める
5. **`role` は一言。** 差し戻しのときに表示される。ここを読んで置き場所が決まる粒度で

## 項目

| 項目 | 何を決めるか |
|---|---|
| `scope.include` / `exclude` | 見る範囲。**生成物を必ず exclude に入れる**(`*.g.dart` 等) |
| `layers[].path` | その層に属するファイル (glob) |
| `layers[].allow` | その層が import してよい層。ここに無い向きは逸脱として出る |
| `layers[].isolate` | 先頭 N セグメントが違う同層どうしの依存を禁じる(機能で切るとき) |
| `limits.file_lines` | 数か、パターンごとのマップ (`{default: 300, "src/api/**": 200}`) |
| `limits.function_lines` / `nesting` / `params` | 関数の長さ / 字下げの段数 / 引数の数 |
| `limits.dir_files` | 1 ディレクトリのファイル数。超えたら分けかたを決めていない印 |
| `comments.min_ratio` / `max_ratio` | コメント行 ÷ コード行。下限と上限 |
| `comments.max_block` / `require_for_lines` | 連続コメントの上限 / 説明を求める関数の長さ |
| `duplication.min_lines` / `ignore` | 行がそのまま重なっているとき何行で言うか / 見ない場所 |
| `duplication.similar` | 形の重なり具合 (0.85 が既定)。**行がそろっていない共通化候補**を出す |
| `duplication.similar_min_lines` / `similar_max_group` | 短い関数は見ない / 大きすぎるかたまりは枠組みの書き方として捨てる |
| `judgments.regrow` | 「このままでよい」と判断したものが何割伸びたら言い直すか (0.3) |
| `dead.entrypoints` / `ignore` / `symbols` | 参照が無くてよい場所 / 見ない場所 / 名前でも見るか |
| `notify.enabled` | 停止時に指摘するか |
| `guard.enabled` / `extensions` / `allow` | 新規ファイルの置き場所を差し戻すか |

## 層をどう切るか

切り方は 2 つしかない。**役割で切るか、機能で切るか。**

| | 役割で切る (layered) | 機能で切る (feature) |
|---|---|---|
| 分け目 | domain / application / infra | cart / order / search |
| 効くとき | 業務の規則が厚い。枠組みを替えうる | 画面が多い。機能ごとに人が分かれる |
| 崩れかた | infra が domain に染み出す | 機能どうしが直接呼び合う |
| 見張り方 | `allow` を狭くする | `isolate` を入れる |

**混ぜてよい。** 外側を機能で切り、各機能の中を役割で切るのが普通。
そのときは `layers` に機能側を書き、`isolate` で機能どうしを離す。

構成そのものの考え方は [references/structure.md](references/structure.md)。

## うるさいと感じたら

**まず規約を疑う。** 直す順:

1. `limits` を実物に合わせる(いちばん多いのはここ)
2. 生成物が `scope.exclude` から漏れていないか
3. `duplication.min_lines` を上げる(8 → 12 で定型の一致がだいぶ減る)
4. `dead.entrypoints` に、枠組みが名前で拾う場所を足す(`src/pages/**` 等)
5. それでも多いなら `notify.enabled: false`。置き場所だけ見るなら `guard` を残す

## 判断台帳 (.code-keeper/judgments.yml)

規約が「何を見るか」を決めるのに対し、台帳は**見た結果どう決めたか**を覚える。
`/code-keeper:review` などが `ck.py judge` で書く。手で書いてもよい。

```yaml
judgments:
  - path: src/components/DangerButton.tsx
    key: "similar:DangerButton:2"     # check の出力にある鍵
    decision: "まとめない"
    why: "危険操作の確認は独立して読めるほうがよい。片方だけ confirm を挟む予定"
    at: 2                             # そのときの大きさ
    date: 2026-09-02
```

3 つの決まりごと:

1. **黙らせたものは消えない。** `check` は必ず件数を出す(`--show-judged` で中身)
2. **永久の免罪符にしない。** `at` から `judgments.regrow`(既定 3 割)伸びたら言い直す
3. **理由を必ず書く。** 理由の無い判断は、次に読む人が覆せない

規約の glob を広げて黙らせるのと違い、台帳は**1 件ずつ・理由つき**で黙る。
「うるさいから全部無効化」を避けるための仕組みで、ここが無いと規約ごと捨てられる。

## 機械が見抜けないこと

このプラグインは構文解析をしない。行の並びと import の書式だけを見る。
だから次は**外す**。規約を書くときに織り込んでおく。

- 動的に呼ぶもの(反射・DI・文字列でのルーティング)は「使われていない」に出る
  → `dead.entrypoints` に入れる
- 生成されたコードは長さと重複の両方で必ず出る → `scope.exclude` に入れる
- 意図的な写し(実験の条件違い、移行中の新旧)は重複に出る
  → `duplication.ignore` に入れる

**出たものは候補。判断は読んでからする。** 指摘が的外れなら、
コードではなく規約か台帳を直す。

そして、**機械が出せないものは規約に書けない**。
名前の不一致・抽象の高さの不揃い・「そのコメントは『なぜ』か言い換えか」・
「形は違うが同じことをしている処理」は、読まないと分からない。
それを見るのが `/code-keeper:review`。規約は「どこを先に読むか」を決めるだけで、
**判断そのものを規約に押し込もうとしない。**
