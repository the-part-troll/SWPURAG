# 招生与图书馆规则边界复审

2026-11-13，Anaconda `SWPU_RAG`。在现有 13 篇文档和 747 个正文块上，沿用 `ask` 默认词法检索和共享 Top 5。实现前冻结 8 道新题及原文判据。冻结文件的 LF SHA-256 为 `79ad3456470990c27bb4258e33f9dd5077544da0a814a97dd6f2fe4b0cd2801c`。[本轮冻结题](../samples/boundary-acceptance.json)

| 题集 | 总题数 | 有必要证据计分的题数 | 修复前 → 修复后 Top 5 全部找齐 |
| --- | ---: | ---: | ---: |
| 原 H 题 | 21 | 15 | 13 → 14 |
| 旧 Q、A、D、F、L 题 | 32 | 24 | 24 → 24 |
| 路由验收题 | 8 | 5 | 5 → 5 |
| 本轮边界题 | 8 | 8 | 5 → 8 |

前后各有 69 条记录，包含分题排名、候选数、每组必要证据是否进入候选以及错范围候选数。旧 32 题和路由验收 8 题的主题、范围和 Top 5 逐题一致。预标注的错范围 Top 5 命中从 H04 一处降至零。全部交付的 Top 5 引文原件均通过重新解析校验，45 项离线测试通过。B07 找到原文，计作检索命中，回答状态另记为 `insufficient`。[修复前逐题记录](boundary-before.jsonl) · [修复后逐题记录](boundary-after.jsonl)

## 逐题核对

数字为必要证据组在共享 Top 5 的名次，`—` 表示缺组。「候选」按不同正文块计数。

| 题 | 修复前 → 修复后 | 核对 |
| --- | --- | --- |
| H04 | 2 → 3 | 来源范围修复。明确报考外校且仅问本部考点，面向报考本校者的 10615 公告候选 38 → 0，章程和目录也因适用对象被排除，总候选 508 → 47。5110 第 27 段说明初试有科目超过三小时不能选本部 5110。 |
| H05 | 1 / 2 → 1 / 2 | 本校报考与考点材料分别保留。章程第 54 段支持报名前征得培养单位同意，5110 公告第 14 段支持上传盖章书面证明。 |
| H06 | 1 / — → 1 / 2 | 第 44 段原已在候选池，因缺考条件被逗号切离，未进 Top 5。修复后按两种情形分别取证，并将完整条件传给 `ask`。 |
| H08 | 1 / — → 1 / — | 收费表的 085901 对应行是章程第 113 段，表头第 105 段仍只作为附加上下文。 |
| H21 | 1 / 2 → 1 / 2 | 招生仍命中 5110 第 36 段；图书馆按 8 月 24 日原到期判适用，9 月 6 日归还包含当天。 |
| B01 | 1 → 1 | 外校、画板类考试。同样在排序前排除 10615，引用 5110 第 27 段。 |
| B02 | 1 / 2、5 → 1 / 2、5 | 同时报考本校和选 5110，10615 第 22 段支持非全日制定向就业；5110 第 13、25 段支持在职证明和近三个月社保材料。 |
| B03 | — → 1 | 仅问主动取消。第 43 段原在候选池但排名漏检，修复后命中。缺考条款第 44 段不进候选。 |
| B04 | 3 → 1 | 仅问确认后未参考。第 44 段升到首位，取消条款第 43 段不进候选。 |
| B05 | — / 3 → 1 / 2 | 合问两种退费情形。第 43 段由候选进入 Top 5，两条各有一个预留批次。 |
| B06 | — → 1 | 范围筛选修复。7 月 10 日原到期、7 月 11 日仍未还、9 月 6 日计划还，三个日期作用不同。公告第 12 段后一条前置条件有据，超期天数连续计算且不扣除。 |
| B07 | 1 → 1 | 7 月 11 日原到期。检索保留第 12 段，回答端识别两条日期范围重叠。 |
| B08 | 1 → 1 | 7 月 12 日原到期在延期范围内，9 月 6 日归还视为不超期。 |

5110 公告第 43 段规定，个人原因放弃报考或填报有误，须在 **2026 年 10 月 24 日 22:00 前**在网报系统取消已缴费的报名，由系统统一处理退费。第 44 段规定，完成网报信息确认但未参加考试者，已缴报名考试费不予退还。H06 和 B05 的实际答复分别引用第 43、44 段，B03、B04 各引用对应一段。[5110 考点公告原件入口](https://www.swpu.edu.cn/gs/info/1074/8650.htm)

暑期公告的两句都位于第 12 段、原件 HTML 第 151 行。前句的延期范围为 7 月 11 日至 9 月 6 日，写明「均含当日」。后句写明 7 月 11 日「含当日」，并限定「已经到期的未归还图书」。B07 的实际 `ask` 完整引用两句，答复仅凭公告无法判定该书是否超期，并建议向图书馆核对。[暑期公告原件入口](https://lib.swpu.edu.cn/1849.8080/noticex/20260710.html)

## 实际问答与附加材料

实际运行 `ask` 核对 H04、H05、H06、H08、H21 和 B01–B08。最终记录有 12 题 `answered`，B07 为带引文的 `insufficient`。B06 两次 `deepseek-flash` 输出均因引文校验拒收，随后用同一 `ask` 入口验证规则答复。B06 和 B07 的最终结果直接引用已匹配的归档条款，分别显示连续计时规则与日期边界重叠，由服务端范围检查生成并通过原文引文校验。另 11 题为 `deepseek-flash` 的实答。按题计的 21 个不同引文编号均可回查。[首轮实际问答](boundary-ask.jsonl) · [B06 模型复测失败记录](boundary-ask-b06-retry.jsonl) · [B06、B07 最终实际问答](boundary-ask-library-final.jsonl)

H08 的 Top 5 只命中收费行，仍按原冻结口径记为未找齐。记录真实模型请求的输入后确认，章程第 105 段随请求传入，标记为 `table_header`、`rank=null`、引文 ID 7。模型在回答中联引该表头和第 113 段，答出 085901 土木工程全日制 8,000 元、非全日制 10,000 元，单位为每生每年。模型请求另外附带了目录表头第 46 段，H08 回答未引用该段。[H08 模型上下文记录](boundary-ask.jsonl)

## 剩余样例

- **排序。** H07 缺少具体复试日期和楼栋。可提示查后续通知的章程第 86 段已进入候选池，仍落在 Top 5 之外。B02 的原冻题找齐两类材料，但将措辞改成「我准备报西南石油大学非全日制硕士，网报是不是得选定向就业？我户口在外省但在四川工作，选本部5110要上传哪些工作材料？」时，10615 第 22 段仍在候选池，却未进 Top 5。
- **回答校验。** B06 前两次 `事实条目缺少可验证的引用` 都发生在生成之后，检索已命中暑期公告第 12 段。最终使用范围检查给出有引文的规则答复。7 月 11 日个案仍需馆方确认，当前归档只能呈现重叠范围。
- **计分口径。** H08 缺组是表头在 Top 5 以外，附加材料与检索分开记。旧 D4 的非全日制证据被当前指定的全日制范围排除，保留原语料的旧标注。

## 运行命令

先激活环境，复跑时显式选择原来默认的 13 篇语料。修复前源码可由提交 `96c1cdd` 提取。当前工作区也保留了 `data/local/boundary-baseline/` 副本。复跑请用新输出文件名。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force data/local | Out-Null
$old = 'data/local/corpus-13-replay.sqlite3'
if (-not (Test-Path -LiteralPath $old)) { python -B -m swpurag --db $old import }
git archive --format=zip --output=data/local/boundary-baseline-source.zip 96c1cdd swpurag/answer.py swpurag/topics.py swpurag/library_scope.py swpurag/catalog_scope.py swpurag/retrieval.py
Expand-Archive -LiteralPath data/local/boundary-baseline-source.zip -DestinationPath data/local/boundary-baseline-source
python -B -m swpurag.routing_eval --db $old --boundary --baseline-source data/local/boundary-baseline-source/swpurag --output reports/boundary-before-repeat.jsonl
python -B -m swpurag.routing_eval --db $old --boundary --output reports/boundary-after-repeat.jsonl
python -B -m unittest discover -s tests -v
```

按 `ask` 约定配置模型环境变量，然后运行原问句。B06、B07 为范围检查分支，可直接离线复现。首轮 H08 的附加材料来自 `request_model` 调用中传入的证据列表，记录了公开证据编号、正文和类型，随后继续执行实际模型请求。

```powershell
$questions = @()
foreach ($file in 'hybrid-admissions', 'hybrid-library-mixed', 'boundary-acceptance') {
  $questions += Get-Content -Raw -Encoding UTF8 "samples/$file.json" | ConvertFrom-Json
}
$ids = @('H04', 'H05', 'H06', 'H08', 'H21') + (1..8 | ForEach-Object { 'B{0:00}' -f $_ })
New-Item -ItemType Directory -Force reports/local | Out-Null
foreach ($id in $ids) {
  $question = ($questions | Where-Object id -eq $id).question
  python -B -m swpurag --db $old ask $question --json | Out-File -NoClobber -Encoding utf8 "reports/local/boundary-$id-repeat.json"
}
```
