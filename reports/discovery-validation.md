# 招生通知栏目采集试验

2026-11-14，在 `SWPU_RAG` 中完成首页发现、筛选、原件归档、独立入库和实际问答。从栏目首页自动发现 20 条候选，先保存计划，随后只请求计划中的两个正文 URL。首页和正文均一次返回 HTTP 200。其余 18 条仅登记，包括已有的 10615、5110 和两份目录的发布页，以及不属于本轮的内容。未访问分页、附件或外部链接。[研究生招生通知首页](https://www.swpu.edu.cn/gs/zsgz/tzgg.htm) · [候选、排除依据和原件](discovery-candidates.md) · [采前计划](../samples/discovery/plan.json)

| 归档来源 | 发布、年度和对象 | 纳入验证库 |
| --- | --- | ---: |
| 8760 网上报名温馨提示 | 研招办转载，页面发布日期 2026-10-19，适用于 2027 年四川网报。原发布机关未署名。 | 15 块 |
| 8710 四川省网上报名解读 25 问 | 研招办转载，页面发布日期 2026-10-08，正文自称「川小招」汇编。适用于 2027 年四川网报，具体考点另有受理条件。 | 51 块 |

两篇均使用省级通用角色 `provincial_general`，与校级招生单位 `admission_unit` 和 5110 考点 `exam_site` 区分。FAQ 完整原件保留。第 19、20、23、24 问的 8 个专项、加分或免初试正文块按原件位置与文字同时校验后排除，保留段落的原件编号不移位。66 个新正文块均重新读取归档、核对 SHA-256 并复核所在段落。两个来源的 URL、实际抓取时刻、哈希、发布信息及适用对象见对应清单。[8760 官网转载](https://www.swpu.edu.cn/gs/info/1074/8760.htm) · [8710 官网转载](https://www.swpu.edu.cn/gs/info/1074/8710.htm) · [录入清单](../samples/discovery/pages.json) · [抓取收据](../samples/discovery/captures.json)

## 独立入库和版本验证

从归档重建 `data/local/discovery.sqlite3`，先导入原有 13 篇文档、747 个正文块，再增至 15 篇文档、15 个版本、813 个正文块。第二次全量离线重放 15 份收据均为 `unchanged`，有效数量相同，尝试记录由 15 增至 30。对验证库的临时副本模拟真实访问失败的 HTTP 403，以及 HTTP 200 但缺少已配置正文容器的响应。两次均记为失败，8760 当前版本、正文和引文位置保持一致。真实抓取均成功，两类失败来自离线合成输入。默认 `data/corpus.sqlite3` 前后 SHA-256 均为 `9016183d37b02aadbde701445e557bd53ee5533e4a138e194ac23ad4d6acbcb7`。[入库、重复与故障留存记录](discovery-import.jsonl)

## B07 漏答修复

B07 单问仍为 `insufficient`，逐字引用暑期公告第 12 段的两句，并提示向图书馆核对。加上研究生续借子问后，整体仍有待核对的个案。还书子问保留同样的两句和提示；续借子问仅给模型对应身份的续借证据，实际答出最多 2 次、每次续借期 30 天，引用读者借阅权限第 5 段。B06、B08 与 H21 的既有适用判断和引文均通过实测，H21 仍分别回答考点重选和延期归还。[B07 单问、合问与回归记录](discovery-ask.jsonl)

## 检索和问答复查

新题在首次运行检索前冻结。验收文件 LF SHA-256 为 `c6ad2abb5782fc613a3c4f223ee44a029000a23d6abc1094fe5bb04860759cce`。沿用默认 `scoped` 词法与共享 Top 5，完整复跑旧 69 题和 8 道新题。77 条记录中的 Top 5 证据均经过原件复核。[新题与判据](../samples/discovery/acceptance.json) · [逐题检索](discovery-retrieval.jsonl) · [69 题扩库前对照](boundary-after.jsonl)

| 题集 | 题数 | Top 5 找齐全部必要证据，扩库前 → 验证库 |
| --- | ---: | ---: |
| H 题 | 21 | 14/15 → 14/15 |
| 旧 Q、A、D、F、L | 32 | 24/24 → 22/24 |
| 路由验收 | 8 | 5/5 → 5/5 |
| 边界验收 | 8 | 8/8 → 8/8 |
| 本轮新题 | 8 | 7/7；另有 1 道个人审核缺证据题 |

| 新题 | 必要组 Top 5 名次 | `deepseek-flash` 实答核验 |
| --- | --- | --- |
| N01 | 3 / 2 | 通过。学信网 APP 在线采集与白底分别引用 8710 第 15、16 段。 |
| N02 | 1 / 2 | 通过。无独立确认阶段、网报期间上传材料，引用 8710 第 7、8 段，另引用第 11 段定位流程。 |
| N03 | 1 | 通过。预报名部分完成者可在正式报名阶段续办，引用 8760 第 7 段。 |
| N04 | 1 | 通过。首轮审核到 10 月 30 日 12:00，补材料到 10 月 31 日 12:00，均引用 8760 第 11 段。 |
| N05 | 4 / 2 | 通过。5110 拒收超过三小时的科目与四川在线拍照分别引用 5110 第 27 段、8710 第 15 段。 |
| N06 | 3 / 1 | 通过。先核对 5110 画板限制，再引用四川省通用选点的限制条件。分别引用 5110 第 27 段、8710 第 31 段。 |
| N07 | 1（缺口背景） | 未通过。库中没有个人缺件及通过时刻。8710 第 21 段可解释「待补充」，模型却追问招生单位及应届身份，未明确指出个人数据缺口，也未引用该段。 |
| N08 | 3 | 通过。报名成功后联系报考点并提供申请表及证明，引用 8710 第 51 段。另引 5110 第 35 段时明确限定本部考点。 |

实际 `ask` 共保存 13 条输出，20 个按题计的不同引用编号均通过原件复核。B07 边界说明和 B06 由已有规则生成，B07 合问的续借部分以及本轮 8 道新题调用了 `deepseek-flash`。[问答、状态与引文结果](discovery-ask.jsonl)

## 剩余问题及发生阶段

- **排序。** 扩库前旧题找齐 51/52，扩库后 49/52。A1 的 5110 第 24 段由第 5 名跌出 Top 5，省 FAQ 第 41 段只说明应届生选点，覆盖不了同题的往届情形。A2 的章程第 26 段由第 4 名跌出 Top 5，省 FAQ 第 43 段是四川自考届时毕业者的材料规则。两组必要证据仍在候选池。
- **适用对象。** 旧题原冻结负例的错范围计数仍为零。人工检查发现新增省 FAQ 的部分段落与旧题所问对象不符，包括 H05 在读硕士题混入第 37 段应届材料，Q2 普通专科题混入第 43 段自考材料，A4 往届材料题混入第 40 段应届小标题。A5 第 33 段的省内总体考位情况也无法证明 5110 个别考点容量。
- **资料与作答。** N07 缺少个人审核信息。相关通用规则检索成功，模型未据此给出明确的缺口说明。该失败与 A1、A2 的排序漏检不同。

## 离线复跑

在 `SWPU_RAG` 环境执行。复跑使用新的输出和验证库文件名。首页筛选可从现存栏目快照离线重放，完整命令见候选报告。[栏目筛选复跑](discovery-candidates.md)

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force reports/local | Out-Null
python -B -m swpurag.discovery_import --db data/local/discovery-repeat.sqlite3 --output reports/local/discovery-import-repeat.jsonl
python -B -m swpurag.routing_eval --boundary --discovery --db data/local/discovery-repeat.sqlite3 --output reports/local/discovery-retrieval-repeat.jsonl
python -B -m unittest discover -s tests -v
```

问答沿用服务端既有模型环境配置。以下命令运行新旧资料合问与 B07 合问，换用冻结清单中的其他题可复核单问和缺证据题。

```powershell
$new = Get-Content -Raw -Encoding UTF8 samples/discovery/acceptance.json | ConvertFrom-Json
$old = Get-Content -Raw -Encoding UTF8 samples/boundary-acceptance.json | ConvertFrom-Json
$question = ($new | Where-Object id -eq 'N05').question
python -B -m swpurag --db data/local/discovery-repeat.sqlite3 ask $question --json
$mixed = ($old | Where-Object id -eq 'B07').question + '另外，我是研究生，图书最多可以续借几次？'
python -B -m swpurag --db data/local/discovery-repeat.sqlite3 ask $mixed --json
```
