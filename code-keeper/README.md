# code-keeper

Claude に順に実装させたコードが、**伸びる・散る・崩れる・残る**のを見張る。

**機械が数え、Claude が読んで判断する。** 数えられることは python が一瞬でやり
(フックと CI で使えるのはここだけ)、数えても答えの出ないことは Claude が
コードを読んで決める。**決めた判断は台帳に残り、同じ指摘は二度と出ない。**

| 困りごと | 機械が出す候補 | 読んで決めるのは |
|---|---|---|
| ファイル・関数が伸びる | 行数 / 関数の長さ / 入れ子 / 引数 | 分ける切れ目があるか。**無いなら分けない** |
| 共通化できるものが散る | 行の一致 + **形の一致**(名前も文言も違ってよい) | 同じ理由で変わるか。**似ているだけならまとめない** |
| 構成が崩れる | import の向きと層の対応 | **この規模・この性格に合った構造か。**規約のほうがずれていることもある |
| コメントが長い / 無い | 比率・連続量・コード片の混入 | それは「なぜ」か、コードの言い換えか |
| 使わないものが残る | どこからも import されない定義 | 枠組みが名前で呼んでいないか |

言語は python / TypeScript / JavaScript / Dart / Go / Rust / Java / Kotlin /
Swift / C# / PHP / Ruby / C / C++ / Scala。`python3` と `git` 以外は要らない。

## 機械と AI の分担

```
書いたとき   → [フック] 数える。速い・毎回同じ・無料。崩れかけを 5 件まで言う
            ↓
読むとき     → /code-keeper:review  Claude がコードを読んで、直すか・このままか決める
            ↓
決めたあと   → [台帳] 判断を理由つきで覚える。3 割伸びたらまた言う
```

**規約に判断を押し込まない。** 「300 行を超えたら分ける」は規約に書けるが、
「このファイルは分けるべきか」は書けない。前者はフックの仕事で、後者は Claude の仕事。

だから機械側は**精度より取りこぼしの少なさ**を優先している。出るのは常に候補で、
[review](commands/review.md) が読んで落とす。落とした理由は台帳に残る。

## 使いかた

```
/plugin marketplace add kosei-matsuzaki/claude-plugins
/plugin install code-keeper@kosei-plugins
```

リポジトリごとに一度だけ:

```
/code-keeper:init
```

現状を測って `.code-policy.yml` を作る。**既存の構成を書き起こすだけで、
勝手に並べ替えない。** 以降はフックがこの規約を見て動く。

### リポジトリの性格で雛形が変わる

| 雛形 | 向き | 分け目 |
|---|---|---|
| [layered-policy.yml](skills/code-policy/references/layered-policy.yml) | サーバ・CLI。業務ロジックが厚い | domain / application / infra |
| [feature-policy.yml](skills/code-policy/references/feature-policy.yml) | 画面のあるもの。React / Next.js / Flutter | 機能ごと(`isolate` で隔てる) |
| [research-policy.yml](skills/code-policy/references/research-policy.yml) | 実験するもの。ML・シミュレーション | src(道具) / experiments(条件) |

**雛形は出発点で、正解ではない。** 適切な構造はプロジェクトごとに違う。
`/code-keeper:review` は実物の import を読んで、**規約のほうを直す提案も出す。**

研究側の肝は **実験ごとの写しを共通化しないこと**。条件を変えた版は「似ているが
別物」で、まとめると過去の実験が再現しなくなる。

## コマンド

| コマンド | 何をするか | 数える / 読む |
|---|---|---|
| `init` | 現状を測って規約ファイルを作る | 数える |
| `check` | 診断する(書き換えない) | 数える |
| **`review`** | **コードを読んで、直すか・このままかを決める** | **読む** |
| `split` | 長いファイル・関数を分ける | 読む |
| `unify` | 同じ / 似た形のコードを 1 つにする | 読む |
| `relayout` | 層の逸脱と置き場所を直す | 読む |
| `comment` | コメントを直す | 読む |
| `prune` | 使われていないものを消す | 読む |

**迷ったら `review`。** どこを見ればいいか(`check`)ではなく、
何をすればいいかを返す。

### 症状からコマンドを引く

| こうなっている | 使うもの |
|---|---|
| このリポジトリで初めて使う | `init` |
| CI で見たい / 全体の件数を知りたい | `check` (`--strict` で終了コード 1) |
| **一区切りついたので見てほしい** | **`review`** |
| 1 つのファイルが長い / 関数が長い / 入れ子が深い | `split` |
| 同じような処理をあちこちで見た気がする | `unify`(**完全一致でなくても出る**) |
| 内側の層が外側を呼んでいる / 構造が合っていない気がする | `relayout` / `review` |
| コメントアウトが残っている / 何をしているか読めない | `comment` |
| 消し忘れたファイルがありそう | `prune` |

### 各コマンドの中身

**`review`** — **このコマンドだけは数えない。読む。** `check` の出力は
「どこから読むか」の順番としてだけ使い、機械が出せないものを探す:
形も名前も違うが同じことをしている処理 / 同じものを指す別々の名前 /
1 つの関数に混ざった高さの違う操作 / そのコメントは「なぜ」か言い換えか /
**そもそもこの構造がこのプロジェクトに合っているか**。
結果を「直す / このままでよい / 規約がずれている」に仕分け、
**このままでよいものは理由つきで台帳に書く。**

**`init`** — 現状を測り(`ck.py measure`)、性格に合う雛形を選んで規約を書く。
上限は実測の 90% 点から始めて下げていく。**最大値に合わせない。**

**`check`** — 書き込みをしない。長さ / 層 / 重なり / 使われていないもの / コメント。
`--since <ref>` で差分だけ、`--strict` で CI 用の終了コード、
`--show-judged` で黙らせているものの中身。

**`split`** — **行数は理由ではなく合図。** import の使われ方が上下で違うか、
説明に「〜して、〜する」が入るかで切れ目を探す。**切れ目が無いなら分けない。**

**`unify`** — 判断は 1 問: **「同じ理由で変わるか」。** 行き先は下(shared / core)で、
横に置かない。引数が 3 つを超えたらまとめ方が間違っているので戻す。

**`relayout`** — 逸脱には「近道の import」「置き場所が違うだけ」「規約が実態に
合っていない」の 3 通りがある。**3 つ目を怖がらない。**

**`comment`** — skill `code-comments` がそのまま作業指示。
コメントアウトされたコードを先に消し、読み取れる説明を消し、
失われた「なぜ」を 1 行に圧縮する。**分からないものには足さない。**

**`prune`** — **間違えると動くコードを消す**唯一のコマンド。`git log` と `grep` で
根拠を取り、一覧を見せて承認を取る。枠組みが名前で拾うものは消さず規約に足す。

## 共通化は「完全一致」では見つからない

行がそのまま重なっているコピペより、**骨組みだけが同じもの**のほうが多い。
名前とリテラルを潰して形だけを比べ、**かたまり**で出す:

```
## 形が似ている関数 (共通化できるかは読んで決める): 3 件
  7 箇所に同じ形 (94%, 最大 15 行)  ui/members_screen.dart:203 _delete() /
    ui/place_picker.dart:147 _delete() / ui/sheets/bag_sheet.dart:80 _delete() ほか 4 件
  4 箇所に同じ形 (99%, 最大 21 行)  data/database.dart:1133 setDocumentPlans() ほか 3 件
```

FE のボタン(同じ骨組みで文言と色だけ違う)は、行の一致では **0 件**、
形の一致では **100%** で出る。組ではなくかたまりで出すのは、
同じ形が 7 箇所にあるとき 21 組の一覧を見せられても直せないから。

枠組みがそう書けと言っているもの(Flutter の `build`、React のコンポーネント本体)は
何十箇所も一致するので、`similar_max_group` より大きいかたまりは捨てる。

**似ていることと、まとめてよいことは別。** 決めるのは `unify` か `review`。

## 判断台帳 (.code-keeper/judgments.yml)

Claude が「このままでよい」と決めたことを覚えておく場所。

```yaml
judgments:
  - path: src/components/DangerButton.tsx
    key: "similar:DangerButton:2"
    decision: "まとめない"
    why: "危険操作の確認は独立して読めるほうがよい。片方だけ confirm を挟む予定"
    at: 2
    date: 2026-09-02
```

- **黙らせたものは消えない。** `check` は必ず件数を出す(`--show-judged` で中身)
- **永久の免罪符にしない。** `at` から 3 割伸びたら台帳を無視して言い直す
- **理由を必ず書く。** 理由の無い判断は、次に読む人が覆せない

これが無いと、同じ誤検出が毎セッション出て、最後は `notify.enabled: false` に
される。台帳はうるささを減らすためではなく、**プラグインが黙らされるのを防ぐため**にある。

## フック

| いつ | 何が起きるか |
|---|---|
| ファイルを書いたあと | 触ったパスを控える(`$TMPDIR/claude-code-keeper/`。リポジトリは汚さない) |
| 新しいファイルを書く前 | 層のどこにも属さない置き場所なら差し戻し、層の一覧を見せる |
| セッションが止まるとき | 崩れかけを**一度だけ**知らせる。止めはしない |

```
code-keeper: 触ったコードが読みにくくなりかけています
・src/domain/user.ts → src/infra/db.ts (domain は infrastructure に依存できない) → `/code-keeper:relayout`
・3 箇所に同じ形 (100%, 最大 9 行)  Button.tsx:2 / DangerButton.tsx:2 / WarnButton.tsx:2 → `/code-keeper:unify`
・src/api/handlers.ts が 412 行 (上限 300) → `/code-keeper:split`
→ 中身を読んで判断するなら `/code-keeper:review`、全体を見るなら `/code-keeper:check`。
```

**同じ指摘はセッション中に繰り返さない。台帳にあるものは最初から言わない。**
触ったファイルに関わるものだけ、最大 5 件。

## 規約ファイル

`.code-policy.yml`(リポジトリの根)。全項目は skill `code-policy`、
構成の考え方は [structure.md](skills/code-policy/references/structure.md)。

```yaml
scope:
  include: ["src/**"]
  exclude: ["**/*.test.*", "**/*.g.dart"]   # 生成物は必ず外す

layers:                       # 層と、依存してよい向き
  - name: domain
    path: ["src/domain/**"]
    role: 業務の規則。枠組みも DB も知らない
    allow: []
  - name: ui
    path: ["src/features/**"]
    allow: [domain]
    isolate: 3                # features/cart と features/order は呼び合わない

limits:
  file_lines: { default: 300, "src/api/**": 200 }
  function_lines: 50
  nesting: 4                  # 字下げの段数。関数の本体を 1 段と数える

duplication:
  min_lines: 8                # 行がそのまま重なっているとき
  similar: 0.85               # 形だけが同じとき (0 で見ない)
  similar_max_group: 12       # これより大きいかたまりは枠組みの書き方
  ignore: ["experiments/**"]

dead:
  entrypoints: ["src/pages/**", "src/main.*"]

judgments:
  regrow: 0.3                 # 判断から 3 割伸びたら言い直す
```

うるさいと感じたら順に:
台帳に書く(1 件ずつ)→ `limits` を実測に合わせる → 生成物が `exclude` から
漏れていないか → `similar` を上げる → `dead.entrypoints` を足す。
全部黙らせるなら `notify.enabled: false`。

## 上限を決めるとき

```bash
python3 .claude/plugins/code-keeper/scripts/ck.py measure
```

```
                        中央     90%    最大    提案
ファイル行数             162     746    3667     900
関数行数                  15      79     365     100
コメント比率             16%     41%    128%  0.08-0.51
```

**コメント比率の既定値は当てにならない。** 5% のリポジトリも 40% のリポジトリも
あるので、必ず測ってから決める。

## 機械には見抜けないこと

行の並びと import の書式しか見ていない(構文解析をしない)。次は必ず外す。

| 外すもの | どうするか |
|---|---|
| 動的に呼ぶもの(DI・反射・文字列でのルーティング) | `dead.entrypoints` に入れる |
| 生成されたコード | `scope.exclude` に入れる |
| 意図的な写し(実験の条件違い、移行中の新旧) | `duplication.ignore` に入れる |
| 外部パッケージと同じ名前の自作モジュール | import の解決を外す |

そして、**そもそも数えられないもの**がある:

- 形も名前も違うが、同じことをしている処理(`for` と `map`)
- 同じものを指す別々の名前 / 違うものを指す同じ名前
- 1 つの関数に混ざった、高さの違う操作
- そのコメントが「なぜ」か、コードの言い換えか
- **この規模・この性格に、その構造が合っているか**

これらは `check` に **1 件も出ない**。出ないことを健全と読まない。
見るのは [`/code-keeper:review`](commands/review.md)。

## CI で使う

```bash
python3 .claude/plugins/code-keeper/scripts/ck.py check --strict
python3 .claude/plugins/code-keeper/scripts/ck.py check --since origin/main --strict
```

**入れるなら `--since` から始める**(既存のコード全部に当てると、
最初の 1 回で真っ赤になって誰も見なくなる)。台帳は git に入れて共有する。

## 前提

`python3`(macOS 標準の 3.9 で動く)と `git`。**追加のパッケージは要らない。**
規約と台帳は YAML の狭い部分集合だけを使い、同梱のパーサで読む。

フックが失敗しても、だまって諦めるだけでセッションは止まらない。
