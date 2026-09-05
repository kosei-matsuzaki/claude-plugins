# claude-keeper

**リポジトリに Claude を導入する入口。**現状を測って規約を作り、このプロジェクトに
要る役・規約・コマンドを `.claude/` に生成する。

**生成したあと、プロジェクトは claude-keeper が入っていなくても回る。**役が読む規約も
日々のコマンドもプロジェクトに置くので、リポジトリを他所へ持っていっても壊れない。

解こうとしている困りごと:

| 困りごと | 効くもの |
|---|---|
| 新しいリポジトリで、毎回ゼロから Claude 用の下ごしらえをする | `/claude-keeper:init` 1 本 |
| docs が実装から離れる・散る・伸びる | 生成される `/docs` + 役 `docs-auditor` |
| 同じ事実が CLAUDE.md と docs の両方にあり、片方だけ古くなる | skill `single-source` + 役 `duplication-auditor` |
| コードが伸びる・散る・崩れる・残る | 生成される `/code` + 役 `code-steward` |
| 作った本人しかいないので、機能の筋を疑う人がいない | 役 `critic` `user-voice` |
| 見た目を好みで決めてしまう / 既定のテンプレートに見える | 生成される `/design` + `docs/design.md` |
| 差分を読まないままコミットが積み上がる | 生成される `/ship` + 役 `reviewer` |
| 収益を求めているのに、機能ばかり足している | 役 `marketer` + `/market` |
| 組んだ `.claude/` が腐る(消えたパスを指し続ける) | 参照切れの検出 / `/claude-keeper:refresh` |
| 作り直すと、手で書いた部分が消える | 生成物の指紋を控えて、手が入ったものは残す |

## 芯にある 2 つの考え

**1. 機械が数え、Claude が読んで判断する。**

数えられることは python が一瞬でやり(フックと CI で使えるのはここだけ)、
数えても答えの出ないことは Claude がコードと docs を読んで決める。
**決めた判断は台帳に残り、同じ指摘は二度と出ない。**

「300 行を超えたら分ける」は規約に書けるが、「このファイルは分けるべきか」は
書けない。前者は機械の仕事で、後者は Claude の仕事。だから機械側は
**精度より取りこぼしの少なさ**を優先し、出るのは常に候補になっている。

**2. 役をサブエージェントに置くのは、速いからではない。会話の記憶を切るため。**

同じセッションで実装した Claude は、自分の実装に肩入れする。悪意ではなく、
**会話に残っているものが証拠に混ざる**から:

- 「時間がないので後で直す」と会話で決めた → 未完成なのに完成として読む
- 設計の理由を会話で説明した → リポジトリに 1 行も無いのに、書いてある気になる
- 3 時間かけて書いた → 捨てる案が候補に入らない

だから役は `.claude/agents/` に置き、**会話の経緯を渡さずに**投げる。
読み方そのものは、プロジェクトに写す規約
[flat-view](templates/skills/flat-view/SKILL.md) に書いてある。

```
組む     → /claude-keeper:init      現状を測って規約を作り、.claude/ を生成する
          ↓
回す     → /standup          ← プロジェクト側のコマンド。claude-keeper は要らない
          ↓
決める   → [台帳] 「いまは直さない」を期限つきで覚える。期限が来たら言い直す
          ↓
組み直す → /claude-keeper:refresh    ずれたぶんだけ。手が入ったものは消さない
```

## 使いかた

```
/plugin marketplace add kosei-matsuzaki/claude-plugins
/plugin install claude-keeper@kosei-plugins
```

リポジトリごとに一度だけ:

```
/claude-keeper:init
```

現状を測って `.claude/policy.yml` を作り、役・規約・コマンドを生成する。
**既存の `.claude/` と `CLAUDE.md` は作り直すが、手で書かれたものは 1 行も消さない**
— 消す前に必ず一覧を見せて聞く。

### リポジトリの性格で雛形が変わる

| 雛形 | 向き | 置く役 |
|---|---|---|
| [default-policy.yml](templates/default-policy.yml) | 道具・ライブラリ。使うのは主に自分 | 4 役 |
| [product-policy.yml](templates/product-policy.yml) | 使う人がいて、収益を求める | 6 役 |
| [research-policy.yml](templates/research-policy.yml) | 回して結果を見る。実験・分析 | 4 役 |

**雛形は出発点で、正解ではない。**`why` が書けない役は置かない。
「あると良さそう」で置いた役は一度も呼ばれず、`.claude/agents/` が
読まれないファイルで埋まる。

## コマンド

claude-keeper が持つのは **3 本だけ**。組む・診る・組み直す。

| コマンド | 何をするか | 書き換える |
|---|---|---|
| **`init`** | **導入の入口。**規約を作り、役・規約・コマンドを生成する | `.claude/` と `CLAUDE.md` |
| `check` | docs・コード・`.claude/` をまとめて診断する | **しない** |
| `refresh` | 生成したときからずれたぶんだけ組み直す | ずれたところだけ |

残りは `init` が**プロジェクトの `.claude/commands/` に生成する**。
プロジェクト専用に書き換わっていて、claude-keeper が入っていなくても動く。

| 生成されるコマンド | 何をするか | いつ |
|---|---|---|
| **`/standup`** | 役を一斉に走らせて一枚にまとめる | 一区切り / 週の頭 |
| `/docs` | docs を実装に合わせ、置き場所を整え、伸びたものを削る | docs がずれたとき |
| `/docs --renew` | docs 全体を棚卸しし、置き場所の決め方から引き直す | 誰も開いていない md が溜まったとき |
| `/code` | 伸びた・散った・崩れた・残ったところを直す | 一区切りついたとき |
| `/code --renew` | 層の切り方そのものを引き直す。規約を先に変えて 1 層ずつ動かす | 構成が実態に合わなくなったとき |
| `/ship` | 差分をレビューし、コミットの切り方まで決める | コミット前 |
| `/critique` | 専門家・使う人として機能と方針にコメント | 機能を足す前 |
| `/design` | 見た目の方向を決めて規定に落とし、画面に当てる。`--renew` で刷新 | 画面を作るとき / 刷新するとき |
| `/routine` | 定期で走らせるものを決めて仕掛ける | 忘れるとき |
| `/market` | 届いていない理由を切り分ける | `marketer` を置いたときだけ |

規約も 5 本写す — `flat-view`(読み方)/ `claude-md`(CLAUDE.md の書き方)/
`docs-style`(文体)/ `single-source`(同じ事実を 2 か所に書かない)/
`code-comments`(コメント)。
**写すものは 1 文字も変えない。**書き換えるのは役とコマンドだけ。

claude-keeper 自身が持つ skill は [policy](skills/policy/SKILL.md) **1 本だけ** —
`init` と `refresh` が読む、規約の書き方と雛形の選び方。生成されるものは
skill ではなく [templates/](templates/) に置いてある。

### 揃えると引き直すを、同じコマンドに持たせてある

`/code` `/docs` `/design` はどれも既定では**決めた形に対して揃える。**
`--renew` を付けると**決め方そのものを引き直す。**別コマンドに割らないのは、
引き直しの半分が「揃える」手順(移動・索引・import の直し)と同じで、
割ると手順が二重管理になるため。

引き直しは 3 本とも同じ骨格を持つ — **いまを数える → 案を 2〜3 出して
選ばせる → 規約を先に書き換える → 1 つずつ動かす → 数え直す。**
最後の「数え直す」があるので、**引き直せたかを言葉ではなく数で言える。**

### `/code` と `/docs` は 1 本に畳んである

読んで「分ける」と決めたらそのまま分けたいので、分ける・まとめる・置き場所を
直す・消す・コメントを直すを別コマンドにする理由が薄い。**手順は薄めずに
節として全部持っている。**`/docs` も同じで、実装に合わせる・置き場所を整える・
長さと文体を直すを 1 本に持つ。

## 生成される `.claude/`

```
.claude/
  policy.yml       規約 1 つ (体制 + docs + code)
  judgments.yml    判断台帳 1 つ
  agents/          役 4〜6
  skills/          flat-view / claude-md / docs-style / single-source / code-comments
  commands/        standup docs code ship critique routine [design] [market]
  manifest.json    生成物の指紋 (機械が書く)
```

## 作り直しても消えない仕組み

`.claude/` を作り直すのは、腐ったものを直すいちばん確実な方法。
ただし**手で書いたものが消えるなら誰も使わない**ので、3 つで守る。

1. **印** — CLAUDE.md の生成部分は `<!-- claude-keeper:generated -->` で囲む。
   **外側は書き換えない**
2. **指紋** — `stamp` で生成時の中身を控える。中身が変わっていれば
   「手が入っている」と分かる。**手が入ったものは黙って上書きしない**
3. **`generate.keep`** — 触ってほしくないものを規約に書く

## 腐るのを見張る

組んだ直後がいちばん正しく、あとは腐る。腐ったことに気づける手がかりは
**機械で数えられる**:

| 数えるもの | なぜ効くか |
|---|---|
| 自立していないか | 規約やコマンドがプラグイン側にしか無いと、持ち出した先で役が壊れる |
| 参照切れ | CLAUDE.md が消えたディレクトリを指すと、Claude はそこを探しに行く |
| 雛形の埋め残し (`{{...}}`) | 埋まっていない役は、役として動かない |
| 土台のずれ | 言語・最上位ディレクトリ・依存・規模が、組んだときと違う |
| 生成物への手直し | 次の作り直しで消える |

スラッシュコマンドから使うぶんには `/claude-keeper:check` でよい。素で叩くときは、
**導入先のパスに版番号が入る**ので探してから呼ぶ:

```bash
K=$(ls ~/.claude/plugins/cache/*/claude-keeper/*/scripts/k.py | head -1)
python3 "$K" check
python3 "$K" check --since origin/main --strict   # CI 用
python3 "$K" measure                              # 上限を決めるとき
```

CI で使うなら、この置き場を clone して `claude-keeper/scripts/k.py` を直に指すほうが確実。

**CI に入れるなら `--since` から始める。**既存のコード全部に当てると、
最初の 1 回で真っ赤になって誰も見なくなる。

**数えられないものは 1 件も出ない。**形も名前も違うが同じことをしている処理、
同じものを指す別々の名前、1 つの関数に混ざった高さの違う操作、そのコメントが
「なぜ」か言い換えか、docs に書いてあることが正しいか、**この規模にその構造が
合っているか** — これらは `/standup` `/code` `/docs` `/critique` が読んで決める。

**ファイル 1 つを見る検査だけでは、散らばりと二重管理が通る。**置き場所も
行数も索引も規約どおりで、仕様だけが 3 つの文書に分かれている状態がそれ。
これを捕まえるのは `docs.overlap`(同じ見出し)/ `docs.duplication`(同じ字面)/
`docs.claude_md`(CLAUDE.md の節が設計書に育っている)の 3 つ。

**3 つとも出すのは場所だけ。**同じ事実かどうかは「変わるときに一緒に変わるか」で
決まり、それは読まないと分からない。決めるのは `/docs` と役
`duplication-auditor`。**言い換えて写した二重管理は機械には 1 件も出ない** —
そこがいちばん見つけにくく、役を置いてある理由。

## 判断台帳 (.claude/judgments.yml)

「このままでよい」「いまは直さない」と決めたことを覚えておく場所。

```yaml
judgments:
  - key: "file_lines"
    path: app/lib/ui/design.dart
    decision: "いまは分けない"
    why: "CLAUDE.md がデザインシステムの出どころを 1 つと決めている。切っても import は 1 行も変わらない"
    at: 3667          # ここから 3 割伸びたら言い直す
    until: 2026-12-01 # 期限を過ぎても言い直す
    date: 2026-09-04
```

- **黙らせたものは消えない。**`check` は必ず件数を出す(`--show-judged` で中身)
- **永久の免罪符にしない。**`at` から 3 割伸びるか、`until` を過ぎたら言い直す
- **理由を必ず書く。**理由の無い判断は、次に読む人が覆せない

台帳はうるささを減らすためではなく、**プラグインが黙らされるのを防ぐため**にある。

## 規約ファイル

`.claude/policy.yml`。手で直してよい。全項目の意味は skill
[policy](skills/policy/SKILL.md)、層の切り方は
[code-structure.md](skills/policy/references/code-structure.md)。

```yaml
project:
  kind: product              # product / tool / library / research
  revenue: subscription      # none なら marketer を置かない

roles:
  - name: critic
    why: 作った本人しかいないので、機能の筋を疑う人がいない
    stance: 同種のアプリを 3 つ使ったことがある人   # ここが役の中身

docs:
  index: docs/README.md      # 索引に無い記録は、無いのと同じ
  layout: [...]              # 置き場所と役割
  watch: [...]               # 「ここを触ったらここを直す」
  claude_md: { max_section_lines: 25 }   # 上限の内側で節が設計書に育つのを捕まえる
  overlap: { enabled: true }             # 同じ見出しが複数の文書に出ていないか

code:
  scope: { include: [...], exclude: ["**/*.g.dart"] }   # 生成物は必ず外す
  layers: [...]              # 層と、依存してよい向き
  limits: { file_lines: 800, function_lines: 80 }       # 実測の 90% 点から
```

**うるさいと感じたときの順番**は skill
[policy](skills/policy/SKILL.md) の「うるさいと感じたら」にある。
いちばん多いのは、生成物が `code.scope.exclude` から漏れていること。

### 統合前の規約からの移行

`docs-keeper` と `code-keeper` は claude-keeper に統合した(2026-09-04)。
**規約ファイルはそのまま読める** — `docs/.docs-policy.yml` と `.code-policy.yml` が
残っていれば `docs:` / `code:` として扱い、判断台帳
(`.code-keeper/judgments.yml` / `.claude/crew-judgments.yml`)も引き継ぐ。
`/claude-keeper:init` が `.claude/policy.yml` 1 つへの移行を提案する
(**値は 1 つも変えない**)。

## フック

**2 本だけ。**

| いつ | 何が起きるか |
|---|---|
| セッションの頭 | 生成したときからずれていれば**一度だけ**知らせる。生成物に手が入っていればそれも |
| 新しいファイルを書く前 | 規約にない置き場所・どの層にも属さない場所なら差し戻す |

停止時には何も言わない。**知らせる hook はセッションに一度だけ**で、
同じことを繰り返さない。

## 言語

python / TypeScript / JavaScript / Dart / Go / Rust / Java / Kotlin / Swift /
C# / PHP / Ruby / C / C++ / Scala。

## 前提

`python3`(macOS 標準の 3.9 で動く)と `git`。**追加のパッケージは要らない。**
規約と台帳は YAML の狭い部分集合だけを使い、同梱のパーサで読む。

フックが失敗しても、だまって諦めるだけでセッションは止まらない。
