---
description: リポジトリに Claude を導入する。現状を測って規約を作り、役・規約・コマンドを .claude/ に生成する
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[--force]"
---

**このリポジトリに Claude を導入する入口。**現状を測って `.claude/policy.yml` を作り、
このプロジェクトに要る役・規約・コマンドを生成するところまでを 1 本で行う。

**生成したあと、プロジェクトは claude-keeper が入っていなくても回る。**役が読む規約も
日々のコマンドもプロジェクトに置く。プラグイン側にしか無ければ、リポジトリを
他所へ持っていった時点で役が壊れる。

**既存の .claude/ と CLAUDE.md は作り直す。ただし、手で書かれたものは 1 行も
消さない。**この 2 つは両立する — 消す前に必ず見せて聞く。

## 1. 現状を見る

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" check
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" measure
```

続けて、性格を読み取るために次を読む:

- `README.md` — 何をするものか、誰に向けたものか
- `CLAUDE.md`(あれば)— **全文**。ここに手で書かれたものが混ざっている
- `.claude/` の中身(あれば)— agents / commands / skills / settings.json を全部
- `docs/README.md`(あれば)— 既にある索引。**ここの分類をそのまま `docs.layout` にする**
- ルート直下のビルド定義と、そこに書かれたコマンド
- ソースの最上位ディレクトリ構成(2 階層まで)と、実際の import の向き
- `git log --oneline -20` — 何が動いているリポジトリか

### 既にあるときは、先に止まる

`.claude/policy.yml` が既にあり `$ARGUMENTS` に `--force` が無ければ、**そこで止めて**
診断だけ報告し、組み直すか聞く。`/claude-keeper:refresh`(差分だけ直す)のほうが安いことも伝える。

`check` が「統合前の規約を読んでいる」と言ったら、**移行だけを先に提案する。**
`docs/.docs-policy.yml` と `.code-policy.yml` の中身を `.claude/policy.yml` の
`docs:` / `code:` にそのまま移し、**値は 1 つも変えない**。承認されたら旧ファイルを
`git rm` する。台帳(`.code-keeper/judgments.yml` 等)も `.claude/judgments.yml` へ寄せる。

## 2. 残すものを決める

作り直しで消えては困るものを、**先に**洗い出す。

| 見つけたもの | どうするか |
|---|---|
| 手で書かれた CLAUDE.md の節 | 中身を丸ごと残す。`<!-- claude-keeper:generated -->` の外に置く |
| `.claude/commands/` にある独自コマンド | 残す。`generate.keep` に書く |
| `.claude/settings.json` の権限・環境変数 | **触らない** |
| 既にある agent で、役として筋が通るもの | 役として取り込む(作り直さない) |
| 空・雛形のまま・使われた形跡が無いもの | 消す候補として挙げる |

**一覧を見せて、1 件ずつ「残す / 作り直す / 消す」の承認を取る。**
git で追跡されていないファイルは戻せないので、特に慎重に。

## 3. 性格を決める

次の 4 つは**推測で決めない**。読み取れなければ聞く。

| 決めること | 読み取れないときは |
|---|---|
| `kind` (product / tool / library / research) | 聞く |
| `users` (誰が使うか。自分だけか) | 聞く |
| `revenue` (収益を求めるか、その形) | **必ず聞く。コードからは絶対に分からない** |
| `bottleneck` (収益を求めるとき、どこで詰まっているか) | 聞く |

`revenue` が `none` / `unknown` なら `marketer` は置かない。
`users` が自分だけなら `user-voice` は置かない。**置かない判断も報告に書く。**

## 4. 規約を作る

雛形は `${CLAUDE_PLUGIN_ROOT}/templates/`。skill `policy` に従う。

| 雛形 | 選ぶ目安 |
|---|---|
| `default-policy.yml` | 道具・ライブラリ。使うのは主に自分 |
| `product-policy.yml` | 使う人がいて、収益を求める |
| `research-policy.yml` | 回して結果を見る |

**雛形を土台に、実測へ寄せる。理想を押しつけない。**

- **`docs.layout`**: 実在する md とディレクトリだけ。`role` は既存の
  `docs/README.md` の説明文から取る(**自分で言い換えない**)
- **`docs.limits` / `code.limits`**: `measure` の **90% 点の切り上げ**から始める。
  **最大値に合わせない**(合わせた上限は何も捕まえない)
- **`docs.watch`**: **2〜3 本だけ。**「ここを触ったらここを直す」。
  `why` は指摘を読んだとき何を直せばいいか分かる一言。**迷ったものは入れない**
- **`code.layers`**: 実際の import の向きを読んで書く。決められないなら**空のまま**に
  する(`/code` が実物から提案できる)。**架空の層を書かない**
- **`code.scope.exclude`**: 生成物を必ず外す(`*.g.*` / `**/generated/**`)。
  ここが漏れると誤検出だらけになって、次の人が機械を信じなくなる
- **`code.comments`**: `measure` のコメント比率を見てから決める。**既定値は当てにならない**

## 5. 役を決める

- **`why` はリポジトリで現に起きている困りごとで書く。**書けない役は置かない
- **`stance` を必ず埋める。**「開発者として」は立場ではない
- `reads` には**実在するパスだけ**書く(空振りする役は使われなくなる)
- 雛形に無い役を足してよい。基準は同じ — 現に困っていること

## 6. 置くものを決める

### 必ず置くもの

| 置くもの | 元 | 加工 |
|---|---|---|
| `.claude/agents/<役>.md` | `templates/agents/<役>.md` | **書き換える** |
| `.claude/skills/{flat-view,claude-md,docs-style,code-comments}/SKILL.md` | `templates/skills/` | **そのまま写す** |
| `.claude/commands/{standup,critique,ship,docs,code,routine}.md` | `templates/commands/` | **書き換える** |

`marketer` を置いたときだけ `.claude/commands/market.md` も置く。

**写すものは 1 文字も変えない。**書き換えるものは `{{ }}` を 1 つも残さない
(埋め残しは `check` が拾う。埋まっていない役は役として動かない)。

### 条件が揃ったときだけ置くもの

判断は [structure.md](../templates/structure.md)。**迷ったら置かない。**

| 見つけたもの | 置くもの |
|---|---|
| 2 段階以上あり、順番を間違えると壊れる手順 | `commands/` にもう 1 本 |
| 破ると壊れる書き方の約束が、コードに一貫してある | `skills/` にもう 1 本 |
| それ以外 | **置かない** |

根拠は**リポジトリの中に既にある**ものに限る。「あると便利そう」で置かない。
**既に CLAUDE.md に書いてあることを skill に写さない** — 二重管理になる。

## 7. 見せてから書く

**書く前に、全部見せる。**規約の全文と根拠(特に `watch` と `layers` は 1 本ずつ)、
置くものの一覧と理由、CLAUDE.md の見出し構成と**残す既存の節**、消すものの一覧。

承認されたら書く。CLAUDE.md は `<!-- claude-keeper:generated -->` で囲み、
**手で書かれた節は印の外に置く**(skill は写した `claude-md` に従う)。

## 8. 控える

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" stamp \
  CLAUDE.md .claude/policy.yml .claude/agents/*.md \
  .claude/commands/*.md .claude/skills/*/SKILL.md
```

控えないと、次に手が入ったことに気づけず、作り直しで消してしまう。

## 9. 最後に

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" check
```

**ここでは直さない。**報告するのは:

- 作った規約と、上限をどう決めたか(実測の何%か)
- 置いた役と、それぞれを**いつ呼ぶか**(1 役 1 行)
- **プロジェクト側に置いたコマンド。**claude-keeper が無くても動くことを伝える
- **置かなかった役と、その理由**
- いま出ている指摘の件数と、どのコマンドで解けるか
