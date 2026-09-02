---
description: このリポジトリの現状を診断して、コード規約 .code-policy.yml を作る
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[--force]"
---

code-keeper の規約ファイルを用意する。**いまの構成を書き起こす。理想を押しつけない。**

## 1. 現状を見る

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ck.py" check
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ck.py" measure
```

`measure` は実物の分布(中央・90%・最大)と、そこから引いた**提案値**を出す。
**上限はこの提案値から始める。** 自分で数字を思いつかない。

規約が既にあり `$ARGUMENTS` に `--force` が無ければ、**そこで止めて**
診断結果だけ報告し、作り直すか聞く。

続けて、規約を推測するために次を見る:

- ソースの最上位から 2 階層のディレクトリ構成(**いちばん重要**)
- ビルド定義(`package.json` / `pyproject.toml` / `pubspec.yaml` / `go.mod` / `Cargo.toml`)
- 既にある lint 設定(`.eslintrc` / `ruff.toml` / `analysis_options.yaml`)— **重複する上限は入れない**
- `CLAUDE.md` / `docs/architecture.md`(あれば)— 既に決めてある構成の意図

## 2. 雛形を選ぶ

skill `code-policy` を読む。`${CLAUDE_PLUGIN_ROOT}/skills/code-policy/references/` の下:

| 雛形 | 選ぶ目安 |
|---|---|
| `layered-policy.yml` | サーバ・CLI。業務ロジックが厚い |
| `feature-policy.yml` | 画面のあるもの。`pages/` `components/` `features/` がある |
| `research-policy.yml` | 実験するもの。`experiments/` `notebooks/` がある、numpy/torch が入っている |

**迷ったら利用者に聞く。** 選んだら、このリポジトリの実態に寄せる。

- **`scope`**: 生成物を必ず `exclude` に入れる(`*.g.dart` `*_pb2.py` `*.d.ts` など、
  実際にあるものだけ)。入れ忘れると指摘の大半が生成物になり、規約ごと無視される
- **`layers`**: **実在するディレクトリだけ。** 3〜5 個。`role` は一言。
  いまの import の向きを見て `allow` を決める。**いまの逸脱を allow に含めない**
  (含めたら見張る意味がない)。逸脱は 4 で数える
- **`limits`**: `measure` の「提案」列をそのまま使う。**最大値に合わせない**
  (1 本の長いファイルのために全体が緩くなる)。90% 点をもとにした値から始めて、
  直しながら下げていく
- **`comments`**: これも `measure` の「コメント比率」から。
  リポジトリによって 5% にも 40% にもなる。**既定値のまま置くと必ず鳴きすぎる**
- **`dead.entrypoints`**: 枠組みが名前で拾う場所(`src/pages/**` `main.*` `conftest.py`)。
  ここを書かないと、動いているコードが「使われていない」と出る
- **`duplication.ignore`**: 意図的な写しがある場所(実験の条件違い、移行中の新旧)

## 3. 見せてから書く

**書く前に、規約の全文と根拠を短く示す。** 特に次の 2 つは 1 つずつ確認する:

- `layers` の `allow` — この向きで合っているか
- `limits` — いまの実測値と、決めた上限を並べて見せる

承認されたら `.code-policy.yml` に書く。

## 4. 最後に

もう一度診断を回す:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ck.py" check
```

**ここでは直さない。** 区分ごとの件数と、どのコマンドで解けるかだけ伝える
(`split` / `unify` / `relayout` / `comment` / `prune`)。

件数が多すぎる区分があれば、**規約が厳しすぎる可能性を先に言う。**
最初から 50 件出る上限は、下げるのではなく上げ直す。
