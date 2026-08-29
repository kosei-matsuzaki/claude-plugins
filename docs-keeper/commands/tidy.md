---
description: 散らかった docs を規約の置き場所に寄せ、索引を貼り直す
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

docs の**置き場所と索引**を整える。中身の書き換えは最小限にとどめる
(文章を削るのは `/docs-keeper:compact`)。
**skill `docs-policy` を読んでから始める。**

## 1. 散らかりを数える

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check
```

見るのはこの 4 つ:

1. **索引に載っていない md** — 誰も辿り着けないファイル
2. **規約にない置き場所の md** — layout から外れたファイル
3. **索引が指しているのに存在しない** — 消したのにリンクが残っている
4. **中身が重なっている md** — 同じことが 2 箇所に書いてある

4 は機械では出ないので、対象ファイルの見出しを一覧して自分で突き合わせる。

## 2. 行き先を決める

各ファイルについて、**1 つだけ**選ぶ:

| 状態 | 行き先 |
|---|---|
| いまの仕様・設計の一部 | 既存の `spec.md` / `architecture.md` の節に**取り込んで削除** |
| 過去の経緯・作業ログ・没案 | `archive/` へ移動 |
| 出すときの手順・掲載文 | `release/` へ移動 |
| 独立した区分として要る | 規約の `layout` に足してから、その場に残す |
| もう誰も読まない | **削除**(git に残る) |

**ファイルを増やす方向には倒さない。** 既存の節に取り込めるならそちらが正解。

## 3. 見せてから動かす

**移動・削除・統合の一覧を先に出して、承認を取る。** 形式:

```
移動  docs/wandering-note.md  →  docs/archive/wandering-note.md   (作業ログ)
統合  docs/db-schema.md       →  docs/architecture.md の「データ層」  (重複)
削除  docs/old-plan.md                                            (方針変更前・archive にも同内容)
残す  docs/supabase_setup.md  →  layout に追加                     (手順として独立)
```

承認されたら `git mv` で動かす(履歴を残す)。

## 4. 貼り直す

- **索引 `docs/README.md` を書き直す。** 表の 3 列目に「いつ読むか」を入れる。
  `archive/` の節には「**いまの仕様として読まないこと**」と明記する
- **リンク切れを全部直す。** 動かしたファイルを指していた箇所を grep して修正
  (`CLAUDE.md` と各 md の相対リンクの両方)
- **規約 `docs/.docs-policy.yml` の `layout` を実態に合わせる**

## 5. 報告

移動・統合・削除の件数、索引の変更点、直したリンク切れの数。
最後に `dk.py check` を回して、1〜3 が空になったことを示す。
