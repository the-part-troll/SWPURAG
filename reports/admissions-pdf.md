# 2027 年非全日制硕士招生专业目录接入与评测

2026-11-12 归档并验证一份 4 页的官网 PDF。目录面向 2027 年普通非全日制硕士考生，拟招生人数列注明不含单独考试。发布页日期为 2026-09-30，PDF 抓取于 2026-11-12 19:13:15（北京时间），HTTP 200，238,204 字节。全日制、单独考试及专项计划目录的考试安排应分别查证。[通知列表](https://www.swpu.edu.cn/gs/zsgz/tzgg.htm) · [目录发布页](https://www.swpu.edu.cn/gs/info/1074/8560.htm) · [附件地址与来源记录](admissions-sources.md) · [本地 PDF 原件](../data/raw/1698135301cac7d50b5386fe0330a6965b8158238eec57c3696ed4ebea2805e3.pdf)

原件 SHA-256 为 `1698135301cac7d50b5386fe0330a6965b8158238eec57c3696ed4ebea2805e3`。官网发布页、附件地址、招生年度和适用对象登记在样本清单，HTTP 状态、抓取时间和校验信息登记在归档清单。[样本清单](../samples/pages.json) · [归档清单](../samples/captures.json)

## 原件和表格核对

沿用文档、版本和正文块结构。该 PDF 形成 59 条方向行证据和 1 条首页拟招生说明。每条行证据含从 1 开始的文件页码、表格及表格行号，并记录左上角原点的行区域坐标和相应单元格位置。行号包含表头、标题和专业行。命令行显示附件链接的 `#page=N`、文件页码、表格行和本地原件。JSON 另保留合并单元格的来源框。

用 Poppler 渲染并逐页检查四页，核对每页重新出现的五列表头和学院归属。该附件的方向行均在单页内结束。学制、科目和备注仅在原单元格区域实际覆盖方向行时继承。专业拟招与方向拟招分别保存，方向人数为空时保留为空。

| 核对位置 | 原件与提取核对 |
| --- | --- |
| 第 1 页表第 5–7 行 | 石油与天然气工程学院的 085706 三个非全日制方向分开提取。油气井工程及油气田开发与海洋油气工程对应 802，油气储运工程对应 801。 |
| 第 2 页表第 24、26 行 | 085404 计算机技术和 085405 软件工程相邻，各自对应本专业表格行与 408 科目。 |
| 第 3 页表第 29–30 行 | 土木工程与测绘学院 125601 的方向为非全日制且不区分研究方向。第 30 行的 199、204 来自覆盖该行的实际合并格，52 是第 29 行的专业拟招人数。 |
| 第 4 页表第 3–4 行 | 经济管理学院同码 085706 的方向为石油与天然气工程管理，第四门是 839。没有继承第 1 页石油与天然气工程学院的科目。 |

第 1 页表第 8 行横跨全表的细分方向编号对照仍可在原件查阅，本次只在相应方向行保留其备注中的编号范围，该全宽行未单独入索引。扫描件、其他表格模板和真正跨页断开的数据行未验证。

## 离线重建和评测命令

本轮 PDF 评测使用 Python 3.12.14、`pdfplumber 0.11.9` 与 `pdfminer.six 20251230`。项目依赖见 [requirements-pdf.txt](../requirements-pdf.txt)。以下 PowerShell 在项目的 Anaconda `SWPU_RAG` 中运行。离线导入只读清单与本地原件，数据库也可另选新路径重建。

```powershell
Set-Location 'P:\SWPURAG'
$env:PYTHONIOENCODING = 'utf-8'
conda activate SWPU_RAG
python -B -m swpurag --db data/admissions-pdf-check.sqlite3 import
python -B -m swpurag import --sample masters-part-time-directory-2027
python -B -m swpurag stats
python -B -m swpurag search '085706 油气储运工程 801' --limit 1
python -B -m unittest discover -s tests -v
```

模型评测沿用[已配置的 DeepSeek 凭据](admissions-evaluation.md)，设 `SWPURAG_MODEL=deepseek-flash`。三条评测命令用问答入口的自然检索与 Top 5；复跑时为输出选择新文件名。

```powershell
python -B -m swpurag.evaluate --generate --method natural --questions samples/admissions-pdf-eval.json --output reports/admissions-pdf-evaluation.jsonl
python -B -m swpurag.evaluate --generate --method natural --only Q2 --only Q3 --output reports/admissions-pdf-regression-q.jsonl
python -B -m swpurag.evaluate --generate --method natural --questions samples/admissions-acceptance.json --only A1 --only A3 --only A5 --output reports/admissions-pdf-regression-a.jsonl
```

隔离库重建为 7 篇文档、7 个版本、427 个正文块。正式库亦已导入。重复导入保留版本与位置，错误归档记录未替换当前版。12 项离线测试通过，逐块重新核对 PDF 的 60 条证据。10 次模型评测均完成且通过输出校验，32 处引用都能回查，其中 14 处为 PDF 引用，18 处为 HTML 引用。引用可回查与答复是否保留全部条件分别判定。

## 目录新题

核对 PDF 原件后、问答前冻结 5 题，清单 SHA-256 为 `4928620b3493f55e6388ff006fdafa6204d7453712e2f2a29af87961d3b8a89e`。5/5 题找齐标注的可支持证据，5/5 题达到预定作答要求。D4、D5 所问的缺失事实单独标注，召回只考察相应可支持部分。[冻结问句](../samples/admissions-pdf-eval.json) · [逐题原始记录](admissions-pdf-evaluation.jsonl)

| 题目 | 必要证据排名 | 回答、范围与引用 |
| --- | --- | --- |
| D1 按 085706 和 03 方向查科目 | 2 | 答出油气储运方向四门，保留英语二或俄语的选择，第四门为 801。引用回查第 1 页表第 7 行。 |
| D2 同码不同学院的第四门 | 3、4 | 分别答出石工院油气井工程 802、经管学院石油与天然气工程管理 839，保留非全日制范围。引用回查第 1 页表第 5 行和第 4 页表第 4 行。 |
| D3 125601 科目与专科工作经验 | 目录 3；章程 2 | 科目引用目录第 3 页表第 30 行，工作经验引用章程第十一条及相应标题。保留专业学位、学院学业要求、同等学力与五年以上工作经验。 |
| D4 能否按非全日制 408 准备全日制考试 | 1 | 说明 408 来自非全日制 085404 的第 2 页表第 24 行，并明确当前缺全日制科目。 |
| D5 085404 最终实际录取人数 | 1 | 说明第 2 页表第 24 行的 10 人为非全日制拟招且不含单考，明确缺最终实际录取数。 |

## 指定回归

五题必要证据均找齐，且必要证据排名与 PDF 入库前的上轮结果一致。A3 的 PDF 目录占了第 4 位，章程两组必要证据仍在第 3、1 位。其他四题 Top 5 没有 PDF。五题使用的都是可回查的 HTML 引用。[Q2、Q3 逐题记录](admissions-pdf-regression-q.jsonl) · [A1、A3、A5 逐题记录](admissions-pdf-regression-a.jsonl) · [入库前结果](admissions-applicability.md)

| 题目 | 必要证据排名，入库前与后相同 | 人工核对与失败样例 |
| --- | --- | --- |
| Q2 普通专科与考点材料 | 年限 1；材料 2、3 | 部分正确。保留普通两年及计算截止点，没有把特殊专业五年用于普通考生。材料句仍漏非应届限定。 |
| Q3 招生单位和考点代码 | 1 | 部分正确。区分 10615、5110，并说明普通统考不会因填 10615 就必须去 5110；本次省略了应届和成人高校应届的具体选点分支，也漏写招生单位特殊要求例外。证据仍在首位。 |
| A1 应往届选点 | 5 | 部分正确。保留就读地、成人高校教学点、其他考生工作地或户籍地，仍漏招生单位特殊要求例外。 |
| A3 专业学位特殊条件 | 经验 3；学习方式 1 | 部分正确。五年限制仍绑定工程管理，且明确仅限非全日制定向。回答句漏写招生学院的学业要求，原条款仍已召回并被引用。 |
| A5 满额与考位数 | 2 | 通过。先答停止缴费和取消后重选，再说明缺考位总量，未给出数字。 |

本轮保留此前原始评测文件。以上回归表中的条件遗漏发生在生成阶段，原件和 Top 5 证据均可核对。
