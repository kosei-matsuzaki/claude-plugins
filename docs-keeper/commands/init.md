---
description: このリポジトリの現状を診断して、ドキュメント規約 docs/.docs-policy.yml を作る
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[--force]"
---

このリポジトリに docs-keeper の規約ファイルを用意する。**既存の構成を尊重して、
いまの姿を書き起こす。** 理想の構成を押しつけない。

## 1. 現状を見る

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check
```

規約が既にあり `$ARGUMENTS` に `--force` が無ければ、**そこで止めて**
現状の診断結果だけ報告する。作り直すか聞く。

続けて、規約を推測するために次を読む:

- `docs/README.md`(あれば)— 既にある索引。**ここの分類をそのまま layout にする**
- `CLAUDE.md`(あれば)— セッション開始時に読むもの、いまの状態
- ルート直下のビルド定義(`pubspec.yaml` / `package.json` / `pyproject.toml` / `Cargo.toml` 等)
- ソースの最上位ディレクトリ構成(2 階層まで)

## 2. 規約を組み立てる

**まず雛形を選ぶ。** `${CLAUDE_PLUGIN_ROOT}/skills/docs-policy/references/` の下:

| 雛形 | 選ぶ目安 |
|---|---|
| `default-policy.yml` | アプリ・ライブラリ・道具。**出すもの**があり、利用者がいる |
| `research-policy.yml` | シミュレーション・機械学習・分析。**回して結果を見る**のが主な仕事 |

見分け方: `experiments/` `notebooks/` `configs/` `data/` `results/` があるか、
`pyproject.toml` / `requirements.txt` に numpy・scipy・torch・sklearn・pandas の
たぐいが入っていれば research 寄り。**迷ったら利用者に聞く。**
研究側の肝は「実験結果を archive へ送らない」こと(理由は skill `docs-policy`)。

選んだ雛形を土台に、このリポジトリの実態へ寄せる。skill `docs-policy` の
「書くときの原則」に従う。

- **`layout`**: 実在する md とディレクトリだけ書く。雛形にあって実在しないものは消す。
  実在するのに雛形に無いもの(`docs/release/` 等)は足す。
  `role` は既存の `docs/README.md` の説明文から取る(自分で言い換えない)
- **`limits`**: いま最も長いファイルの行数を見て、その **1.2 倍を切り上げた値**から始める。
  `archive` 配下は 2000 か、上限なし
- **`watch`**: ここが肝心。**2〜3 本だけ**作る。作り方:
  - ソースの中で「変わったら設計の説明が変わる」中核ディレクトリ → `architecture.md`
  - 画面 / API / CLI の入口にあたるディレクトリ → `spec.md`
  - バージョン・依存を定義するファイル → `changelog.md`
  - `why` は「設計の核が動いた」のように、**指摘を読んだとき何を直せばいいか分かる**一言
  - 迷ったものは入れない。鳴りすぎる規約は読まれなくなる
- **`guard.scope`**: `docs/**` と `*.md`。アプリのソース内 README を巻き込まないこと
  (`app/README.md` などが既にあるなら scope から外れていることを確かめる)。
  notebook の置き場所も見張るなら `guard.extensions` に `".ipynb"` を足す
  (ただし **notebook が自動生成される場所があるなら足さない**)
- **`archive`**: `index` を必ず置く(記録は引けなければ無いのと同じ)。
  `rotate.by` はリリースがあるものなら `version`、無ければ `year`。
  `rotate.max_lines` は**いちばん長い記録の 1.2 倍**から

## 3. 見せてから書く

**書く前に、提案する規約の全文と、その根拠を短く示す。** 特に `watch` の各行は
「この対応でいいか」を確認する。承認されたら `docs/.docs-policy.yml` に書く。

## 4. 最後に

規約を書いたあと、診断をもう一度回して、いま規約に反しているものを一覧にする:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dk.py" check
```

**ここでは直さない。** 何件あるかと、`/docs-keeper:tidy`(置き場所と索引)
`/docs-keeper:compact`(長さと冗長さ)のどちらで解けるかだけ伝えて終わる。
