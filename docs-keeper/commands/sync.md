---
description: 実装の変更を docs に反映する。最小差分で、記録は archive へ
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[--since <git-ref>]"
---

実装が変わったのに docs が追いついていない箇所を埋める。
**skill `docs-style` と `docs-policy` を読んでから始める。**

## 1. 何が変わったかを集める

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check $ARGUMENTS
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" session
git status --short && git log --oneline -15
```

`$ARGUMENTS` に `--since <ref>` があればそれを起点にする。無ければ
「未コミットの差分 + このセッションで触ったファイル」が対象。

次に、**変更の中身を実際に読む**(`git diff` と該当ファイル)。
ファイル名だけで docs を書き換えない。**何が変わったのかを理解してから書く。**

## 2. 反映先を決める

規約の `watch` が指す docs を出発点にしつつ、内容から判断する。

| 変わったもの | 反映先 |
|---|---|
| 振る舞い・画面・できること | `spec.md` |
| 構造・データの持ち方・設計判断 | `architecture.md` |
| 利用者から見える変化 | `changelog.md` |
| 作業前に知らないと壊すこと・新しい罠・コマンド | `CLAUDE.md` |
| 済んだ作業 | `TODO.md` から消して `archive/` へ |
| なぜそう決めたか・試して捨てた案 | `archive/` **だけ** |

**判断に迷う変更は書かない。** 何を書かなかったかを最後に報告する。

## 3. 書く

- **最小差分。** 該当する節だけ直す。周りの文章を「ついでに」整えない
  (整えるのは `/docs-keeper:compact` の仕事)
- **いまの姿だけを書く。**「〜だったが〜に変えた」は仕様書に書かない。
  経緯が要るなら `archive/` に日付つきで書き、仕様書には結論だけ 1 行
- **重複を作らない。** 同じ説明が既に他のファイルにあるなら、そちらへリンクする
- **`TODO.md` から済んだ項目を消す。** 消した項目は `archive/work-log.md` へ
  日付つきで移す(無ければ規約の `archive.dir` 配下に作り、索引にも足す)
- **索引を直す。** ファイルを増減させたら `docs/README.md` の表を必ず更新する
- **嘘を書かない。** コマンド・パス・バージョンは書く前に実在を確かめる

## 4. 報告

- 直したファイルと、**何行から何行になったか**
- 反映した内容を 1 件 1 行で
- **書かなかった変更と、その理由**(判断がつかなかった / docs に書くことではない)

最後に検算する。ここが空になっていれば完了:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check
```
