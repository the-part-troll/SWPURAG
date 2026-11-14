# 15 篇验证库扩库验收

2026-11-14。在同一份 `data/local/discovery.sqlite3` 上用默认 `scoped` 词法检索、共享 Top 5 复跑现有 77 题与 5 道新冻结题。修复前后验证库均为 15 篇、813 块，SHA-256 为 `1439fc2182a621c7a6fe4d2706b55c87959d8475d1a0db760201307f976378f6`。默认库保留 13 篇，前后哈希均为 `9016183d37b02aadbde701445e557bd53ee5533e4a138e194ac23ad4d6acbcb7`。本轮交付的是扩库验收结果。[修复前逐题记录](expansion-before.jsonl) · [修复后逐题记录](expansion-after.jsonl)

| 题集 | 题数 | 找齐必要证据，修复前 → 修复后 |
| --- | ---: | ---: |
| 扩库试验前已有题 | 69 | 49/52 → 51/52 |
| 上轮扩库验收题 | 8 | 7/7 → 7/7 |
| 本轮补充题 | 5 | 3/3 → 3/3 |

澄清与个人资料缺失题的背景证据单列。82 题逐组比较，修复前已命中的必要组均保留。4 道旧题的新增错范围标注从 4 题命中降至 0，E01 的错范围命中也已排除。前后各 82 条检索记录均通过归档校验，48 项离线测试通过。冻结文件和错范围附加标注在首次运行新题前写入，原 77 题判据沿用。[5 道补充题](../samples/discovery/expansion-acceptance.json) · [旧题附加错范围标注](../samples/discovery/expansion-negatives.json)

## 证据用途与适用对象

用 SQLite 只读模式对修复前代码进行 Top 6 诊断，确认 A1 的 5110 公告第 24 段和 A2 的招生章程第 26 段都位于第 6。修复后评测使用 Top 5。规则按来源角色和可回查的原文词组识别问答段落，再匹配问句的任务与人群。双人群选点规则和普通专科资格可各保留一个候选位置，由现有词法排序、去重和 Top 5 合并。规则使用段落文本判断适用范围，沿用现有验证库字段。[5110 考点公告原件](../data/raw/1b734cc864f976fdfbc821944d8ed67d971cdf337e2ba1fe7ab432a80eb632ff.html) · [招生章程及取用沿革](admissions-applicability.md)

| 题 | 修复前 | 修复后 |
| --- | --- | --- |
| A1 | 5110 第 24 段第 6，省 FAQ 第 41 段第 4 | 5110 第 24 段第 1，覆盖应届、往届与例外。FAQ 第 41 段第 2，只补充应届情形。 |
| A2 | 章程第 26 段第 6，混入 FAQ 第 43 段自考材料 | 章程第 26 段第 1，正文明确国家承认的高职专科毕业后至录取当年入学前满两年，按本科毕业同等学力报考。 |
| H05 | FAQ 第 37 段应届材料在第 2 | 应届材料标题及回答退出候选。在读研究生的章程与考点材料分别第 1、第 2。 |
| Q2 | FAQ 第 43 段自考届时材料在第 4 | 自考届时毕业材料退出候选，普通专科年限与考点材料共两组均命中。 |
| A4 | FAQ 第 40 段应届选点标题在第 5 | 应届选点、应届资料标题与回答退出候选，往届材料保持第 1。 |
| A5 | FAQ 第 33 段全省考位统计在第 2 | 省级统计退出候选，5110 缴费额满条款第 2。当前资料缺 5110 总容量。 |
| N05、N06 | 均找齐省级通则及 5110 条款 | 必要组排名分别为 4 / 2、3 / 1，实答均联引两类材料。 |

补充题 E01 的外省高校应届选点命中 FAQ 第 41 段，之前混入的自考第 43 段已排除。E02 在川自考届时可毕业材料仍命中第 43 段，章程普通专科年限段不参与其取证。E03、E05 的状态规则均由第 2 升至第 1。E04 个人状态背景和公开补件截止由「第 2、缺失」变为「第 1、第 2」。[同库前后完整位置与候选](expansion-after.jsonl)

## DeepSeek 实答与引文复核

用 `deepseek-flash` 按默认检索运行 8 道指定和对照题。按题去重的 11 个引文编号均能从原件重新解析定位。Q6 为正常澄清，无引文。个人审核识别后，只将公开状态或时限的问题和对应证据交给模型，程序单独说明个人审核数据缺口。[实际 ask 及引文核对](expansion-ask.jsonl)

| 题 | 实答核验 |
| --- | --- |
| A1 | `answered`。应届原则上按就读地，成人高校应届可选教学点，其他考生按工作或户籍所在地，并保留招生单位特殊要求的例外。引用 5110 第 24 段，另引 10615 第 33 段。 |
| A2 | `answered`。专科毕业到录取当年入学前满两年及以上，以本科毕业同等学力报考，引用章程第 26 段。 |
| N05 | `answered`。5110 三小时限制与四川省用学信网 APP 在线拍照分别引用 5110 第 27 段和 FAQ 第 15 段。 |
| N06 | `answered`。四川合条件可选考点须受具体考点限制约束。画板考生不能选 5110，分别引用 FAQ 第 31 段与 5110 第 27 段。 |
| N07 | `insufficient`。引用 FAQ 第 21 段解释「待补充」，明确无法确认个人缺件或通过时间，提示查看研招网本人页面审核意见或联系所选报考点。扩库首轮的无关身份追问已消除。 |
| E04 | 个人分支 `insufficient`，公开时限分支 `answered`。分别引用 FAQ 第 21 段与网报提示第 11 段，后者支持 **2026 年 10 月 31 日 12:00 前**补材料。答复按 2027 招生年度表述时间点，未将个人审核通过时间等同于公开时限。 |
| Q6 | `clarify`。先问西南石油大学是希望报考的招生单位，还是要选的考试报考点。 |
| N04 | `answered`。首轮审核 10 月 30 日 12:00 前，考生补材料 10 月 31 日 12:00 前。两条均引用网报提示第 11 段。 |

旧题唯一仍未找齐的是 H08。收费行在榜首，表头仍作为额外 `table_header` 供问答使用，按原口径不计入 Top 5。H07 具体复试时间和楼栋仍缺资料，定位查询指引的章程第 86 段仍在 Top 5 之外。错范围结果仅覆盖冻结标注。本次保留了原有 69 题及扩库 8 题，并补充了 5 道验收题。[H08 既有问答与表头验证](boundary-regression.md)

## 复跑命令

以下命令从提交 `420cf83` 取修复前源码，在同一份验证库中以只读 SQLite 模式复跑对照。输出文件使用独占创建，重复运行使用新的文件名。若缺少验证库，先按上轮命令离线重建。[验证库离线重建](discovery-validation.md#离线复跑)

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force data/local,reports/local | Out-Null
$baseline = 'data/local/expansion-replay-source'
New-Item -ItemType Directory $baseline | Out-Null
git archive --format=zip --output="$baseline/before.zip" 420cf83 swpurag/retrieval.py swpurag/catalog_scope.py swpurag/topics.py swpurag/library_scope.py swpurag/answer.py
Expand-Archive -LiteralPath "$baseline/before.zip" -DestinationPath $baseline
$db = 'data/local/discovery.sqlite3'
python -B -m swpurag.routing_eval --boundary --discovery --expansion --db $db --baseline-source "$baseline/swpurag" --output reports/local/expansion-before-repeat.jsonl
python -B -m swpurag.routing_eval --boundary --discovery --expansion --db $db --output reports/local/expansion-after-repeat.jsonl
python -B -m unittest discover -s tests -v
```

模型沿用 `ask` 的环境变量设置。命令通过实际 `ask` 入口保存逐题输出、并回查每个引用的原件。`--only` 可用于指定题目复测。[模型环境配置](../README.md)

```powershell
$env:SWPURAG_MODEL = 'deepseek-flash'
python -B -m swpurag.expansion_ask --db $db --output reports/local/expansion-ask-repeat.jsonl
```
