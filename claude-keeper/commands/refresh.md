---
description: 生成したときからずれたぶんだけ組み直す。手が入った生成物は消さない
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[役名 | コマンド名 ...]"
---

`init` は全部作り直す。`refresh` は**ずれたところだけ**直す。
「土台が動いた」と言われたら、たいていこちらで足りる。

## 1. ずれを見る

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" drift
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" check --only crew
```

| ずれ | 直しかた |
|---|---|
| 土台が変わった(ディレクトリ・言語・依存・規模) | `reads` と `code.scope` と CLAUDE.md の構成を合わせる |
| 生成物に手が入った | **中身を読む。手のほうが正しいことが多い**(2 節) |
| 自立していない(規約が写されていない / コマンドが無い) | 写す・置く |
| 写した規約が写し元と違う | 写し直す。**手で直していたなら 2 節へ** |
| 参照切れ・雛形の埋め残し | パスを直す / 穴を埋める |
| 統合前の規約・台帳が残っている | `.claude/policy.yml` と `.claude/judgments.yml` へ寄せる |

## 2. 手が入ったものを先に片づける

**ここを飛ばすと、人の書いたものを消す。**

```bash
git log --oneline -3 -- <パス>
git diff HEAD -- <パス>
```

| 見えたもの | どうするか |
|---|---|
| 手の直しが正しい | **取り込む。**生成の側(雛形)を直して、次から同じものが出るようにする |
| 手の直しが古い | 上書きしてよいか**聞く**。理由を添えて |
| 判断できない | 上書きしない。そのまま残して報告に書く |

## 3. 役と規約を見直す

土台が変わったなら、要るものも変わっている。

| 変わったこと | 見直すもの |
|---|---|
| 画面・入口ができた | `user-voice` を足すか。`/design` と `docs/design.md` も |
| 使う人が自分だけになった | `user-voice` を外すか |
| 収益を求め始めた / やめた | `marketer` と `/market` を足す / 外す |
| ソースが大きく増えた | `code.scope` / `code.layers` / 上限を測り直す |
| docs の置き場所が変わった | `docs.layout` / `docs.index` |
| **構成が実態に合っていない** | ここでは直さない。**`/code --renew`** の仕事 |
| **誰も開いていない md が溜まった** | ここでは直さない。**`/docs --renew`** の仕事 |
| 規約に無い節が雛形に増えた | 雛形から**その節ごと写す**(下) |

### 雛形に増えた節を写す

`${CLAUDE_PLUGIN_ROOT}/templates/*-policy.yml` と `.claude/policy.yml` の
キーを見比べ、**規約に無い節があれば写す。**既定値で動いてはいるが、
規約に書いていない設定は**次に読む人に見えない**ので直せない。

いま写す対象:

| 写すもの | 何のため |
|---|---|
| `docs.claude_md` / `docs.overlap` / `docs.duplication` | 散らばりと二重管理を見る |
| `.claude/skills/single-source/SKILL.md` | 同じ事実を 2 か所に書かせない(予防) |
| `.claude/agents/duplication-auditor.md` + `roles:` の 1 行 | 二重管理を探す役(検知) |
| `.claude/commands/design.md` + `docs/design.md` | 見た目を決めて画面に当てる(**画面があるときだけ**) |

**役を足したら `roles:` にも書く。**ファイルだけ置くと `check` が
「体制に無い agent」と言い続ける。docs が 1 枚しか無いリポジトリでは
`duplication-auditor` を置かない(突き合わせる相手がいない)。

- **値は雛形のまま写す。**このリポジトリに合わないと分かってから緩める
- 写したら `check --only docs` を回す。**新しく出た指摘は `/docs` の仕事**で、
  ここでは直さない。件数と中身を報告に載せる

**足す役より、外す役を先に考える。**一度も呼ばれていない役は、
要らなかったのではなく**呼ばれ方が分からなかった** — 外すか、command から名指しで呼ぶ。

上限を測り直すときは `k.py measure`。**実測の 90% 点から。**

## 4. 直す

**書き換える前に一覧を見せて承認を取る。**`init` と違って全部は作り直さない。

- CLAUDE.md は `<!-- claude-keeper:generated -->` の**内側だけ**書き換える
- `generate.keep` に挙がっているものは触らない
- 役やコマンドを消すときは、対応するファイルも消す(残ると `check` が言い続ける)
- `.claude/policy.yml` も実態に合わせて直す

`$ARGUMENTS` に名前があれば、そこだけを見直す。

## 5. 控え直す

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" stamp \
  CLAUDE.md .claude/policy.yml .claude/agents/*.md \
  .claude/commands/*.md .claude/skills/*/SKILL.md
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/k.py" check
```

`stamp` を忘れると、次のセッションでも「手が入っている」と言われ続ける。

## 報告

- 取り込んだ手直しと、雛形をどう直したか
- 足した / 外した役・コマンドと、その理由
- **上書きしなかったもの**(判断できなかったもの)を必ず挙げる
