# 本地问答演示复审记录

2026-11-13，Windows，Anaconda `SWPU_RAG`（Python 3.12）。使用原有的 13 篇文档、747 个正文块和 `deepseek-flash`，未扩充语料。浏览器与 `ask` 共用 `answer_question`，检索方式为 `scoped`，Top 5。表头等必要引用上下文由原链路附加，页面与排名结果分开计数。

## 启动、关闭与对照

在已配置模型环境变量的终端启动。尚无样本库时先执行 `python -B -m swpurag import`。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
python -B -m swpurag serve --port 8765
```

在浏览器访问 `http://127.0.0.1:8765/`。按启动终端的 `Ctrl+C` 停止。若 `conda` 启动器不可用，可使用 `C:\Users\libai\anaconda3\envs\SWPU_RAG\python.exe` 执行相同命令。模型配置沿用 `ask`；生成时问题和检索到的公开证据发送给配置的模型服务。

在另一终端用同一个环境和模型逐题运行：

```powershell
python -B -m swpurag ask --retriever scoped --limit 5 --json '<表中的原问句>'
python -B -m unittest discover -s tests -v
```

离线测试 31 项全部通过，包含 4 项本地 HTTP 测试。`node --check swpurag/web/app.js` 通过。

## 浏览器逐题核验

通过桌面内置 Chromium 实际填写并提交。对照 `ask --json` 的状态、主题状态和引用指向，同一事实的模型措辞允许有差异。P 是 [2027 年全日制目录](https://www.swpu.edu.cn/gs/info/1074/8540.htm) 第 6 页表格第 22 行；H 是 [延长图书馆开放时间的通知](https://lib.swpu.edu.cn/1849.8080/noticex/20261019.html) 正文块 2，HTML 第 116 行第 1 列。

| 问句 | 浏览器实测 | 命令行对照与引文 |
| --- | --- | --- |
| 计算机与软件学院全日制085404初试第四门是什么？ | 已找到依据；答 408 计算机学科专业基础。 | 首次模型连接报 `SSL: UNEXPECTED_EOF_WHILE_READING`，单次复核为 `answered`；事实与出处 P 一致（浏览器、CLI 均引用 `[1]`）。 |
| 2026年12月18日晚上十点十分，我还能在成都二期图书馆自习吗？ | 已找到依据；成都分馆适用，22:10 在临时开放时段内，截止 22:30；引文卡保留 10 月 19 日至 12 月 18 日的生效日期。 | `answered`；两端均引用 H `[1]`。 |
| 计算机与软件学院全日制085404初试第四门是什么？另外，2026年11月20日成都总馆晚上开到几点？ | 两个主题分别显示，硕士招生答 408，图书馆答总馆临时开放至 22:30。 | 整体和两个主题均为 `answered`；两端分别引用 P `[1]`、H `[2]`。 |
| 2026年8月1日，成都校区图书馆晚上几点关门？ | 需要补充；询问成都一期总馆还是二期分馆，未猜测关门时间。 | `clarify`；两端澄清一致，无引文。 |
| 成都总馆今晚八点还剩多少个自习座位？ | 证据不足；说明存档没有该时点的实时余座信息。 | `insufficient`；两端缺口一致，无引文。 |
| 计算机与软件学院全日制085404初试第四门是什么？另外，成都总馆今晚八点还剩多少个自习座位？ | 部分已回答；招生仍答 408 并显示 P `[1]`，图书馆一节单独说明实时余座缺口。 | 整体 `insufficient`，招生 `answered`，图书馆 `insufficient`；页面将有答案且存在缺口的整体状态显示为「部分已回答」。引用位置一致。 |

## 出处抽查与模型故障

- **HTML**：临时开放回答的 `[1]` 指向证据卡，官网链接为 H；点击本地原件，浏览器打开 `3b8bd6329b4fab91e9ca6f3c0c8f7f87f67ebc7be12e6eb137f8489e77136eb9.html#L116`。第 116 行是段落起始的 `<p>`，下一行即总馆、分馆在 10 月 19 日至 12 月 18 日开放至 22:30 的原文。查看器用带行号的纯文本显示原件。
- **PDF**：招生证据卡显示第 6 页、表格第 22 行和官网附件。点击本地原件，浏览器 PDF 查看器显示第 6 / 11 页。归档 SHA-256 为 `c2e284441dfdfb8ae661e7c3662a21aaccb3be5bbf21038649d2ce885a43507f`；离线按行坐标核对 01 全日制方向与覆盖相邻两行的考试科目合并格，其中第四科是 408。表格行号按解析顺序计，PDF 查看器只跳页。
- **模拟模型故障**：在下面的模拟服务上提交第一题，页面显示「回答暂不可用，请检查本地模型配置后重试」，没有生成答案引文，仍可查看检索到的原文，模拟的供应商错误详情未显示。

在项目目录执行以下 PowerShell 命令，打开 `http://127.0.0.1:8766/`，复核后按 `Ctrl+C` 关闭：

```powershell
@'
from pathlib import Path
from unittest.mock import patch
from swpurag.answer import AnswerError
from swpurag.server import serve

with patch("swpurag.answer.request_model", side_effect=AnswerError("simulated provider failure")):
    serve(Path("data/corpus.sqlite3"), Path("data"), 8766)
'@ | python -B -
```

## 已知边界

- 实测使用的是已归档资料。演示无实时座位接口，也不会自动刷新公告；超出馆舍或日期适用范围时，由原问答链路澄清或报告缺口。
- PDF 行号由页面显示；跳页取决于浏览器的 PDF 查看器。HTML 原件是带行号的源文本，官网没有段落锚点时，官网链接打开的是整页。本轮回查使用本地原件。
- 生成依赖配置的模型和网络。首次命令行 TLS 失败保留在逐题记录；后续同题成功。服务端返回可读提示，详细模型错误可通过单独运行 `ask --json` 查看。
