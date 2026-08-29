---
name: docs-policy
description: リポジトリごとのドキュメント規約 docs/.docs-policy.yml の読み方・書き方・既定値。docs の置き場所、索引、行数上限、実装とドキュメントの対応表を決めるときに使う。/docs-keeper:init /sync /tidy /compact の土台。
---

# ドキュメント規約 (docs/.docs-policy.yml)

**規約はリポジトリごとに決める。** 共通の正解を押しつけない代わりに、
決めたことはファイルに書いて、フックとコマンドがそれを見る。

規約ファイルの場所(上から順に探す):

1. `docs/.docs-policy.yml`(既定)
2. `docs/.docs-policy.yaml`
3. `.claude/docs-policy.yml`

雛形は [references/default-policy.yml](references/default-policy.yml)。
構成の考え方は [references/structure.md](references/structure.md)。

## 各項目の意味

| キー | 何を決めるか | 効き先 |
|---|---|---|
| `index` | 索引ファイル。全 md はここから辿れること | Stop フック / tidy |
| `layout` | 置き場所と、そこに何を書くか | Write フック / tidy |
| `limits` | ファイルごとの行数上限 | Stop フック / compact |
| `watch` | 「ここを触ったらここを直す」の対応表 | Stop フック / sync |
| `archive` | 記録の置き場所と、archive へ送る決まり | compact |
| `notify` | 停止時に指摘するか、何件から指摘するか | Stop フック |
| `guard` | 規約にない置き場所への新規 md を差し戻すか | Write フック |

## 書くときの原則

- **`layout` は実在する場所だけ書く。** 理想の構成ではなく、いまの構成 +
  これから寄せたい先。存在しない場所を書くとフックが的外れに鳴る
- **`watch` は「変えたら必ず docs が変わる」対応だけ書く。**
  疑わしいものを足すと、鳴るのが当たり前になって誰も読まなくなる。
  最初は 2〜3 本から始めて、鳴らなくて困ったときに足す
- **`limits` は現状の 1.2 倍くらいから始める。** いきなり厳しくすると
  全ファイルが赤くなって意味を失う。archive 配下は上限を外すか大きく取る
- **`role` は一言で書く。**「いまの仕様」「記録。仕様として読まない」のように、
  読み手がそのファイルを開くかどうか判断できる粒度で

## 変更するとき

規約は動かしていい。むしろ、フックが的外れに鳴ったら**まず規約を疑う**。

- 鳴りすぎる → `watch` の対応を削るか `notify.min_source_edits` を上げる
- 新しい区分の md が要る → `layout` に足してから書く(逆順にしない)
- しばらく黙らせたい → `notify.enabled: false`。`guard.enabled: false` は別枠
