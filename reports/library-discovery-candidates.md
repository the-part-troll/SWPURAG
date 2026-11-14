# 图书馆通知栏目采集记录

栏目配置 `library` 限定 `lib.swpu.edu.cn` 上的 `/1849.8080/noticex/`。首页只解析默认可见的 `ul#page_ul_1`，取带日期的公告链接。归档首页的默认列表有 30 项，其中 28 项的 URL 符合本轮正文路径规则，2 项带 `.2.html` 或 `.3.html` 后缀，仅保留在首页原件中。采集器每轮最多请求 4 个正文 URL，不跟随重定向。[图书馆通知公告](https://lib.swpu.edu.cn/1849.8080/noticex/index.html)

[候选清单](../samples/library-discovery/plan.json)于 2026-11-14 19:49:31（北京时间）落盘。28 项中选取两份，本轮待核验的节假日安排和较早的延时通知都可直接从默认列表发现。其余 26 项仅登记，其中包含已有的 2026 年延时和暑期通知，以及范围外的活动、培训和其他假期通知。两份正文从 19:49:51 起各请求一次，均成功。没有访问附件或其他正文。

| 首页原件行号 | 公告 | 处理及依据 |
|---:|---|---|
| 84 | [2026 年中秋、国庆开放安排](https://lib.swpu.edu.cn/1849.8080/noticex/20260915.html) | 采集。用于补齐 10 月 2 日闭馆和同一假期其他日期常规开放的依据。 |
| 104 | [2025 年延时开放](https://lib.swpu.edu.cn/1849.8080/noticex/20251020.html) | 采集。按地址及适用日期区分同名公告。 |
| 80 | [2026 年延时开放](https://lib.swpu.edu.cn/1849.8080/noticex/20261019.html) | 登记。已有样本 `library-chengdu-2026-autumn-extension` 和归档原件，本轮复用。 |

## 采集及原件核对

[首页收据](../samples/library-discovery/listing.json)和[正文收据](../samples/library-discovery/captures.json)记录原地址、最终地址、HTTP 状态、抓取时间、内容类型和 SHA-256。以下三个响应均为同址 HTTP 200、`text/html; charset=utf-8`。使用采集器的归档读取函数离线复核 SHA-256。

| 原件 | 请求时间（北京时间） | 字节 | SHA-256 与原件 |
|---|---|---:|---|
| 栏目首页 | 2026-11-14 19:47:06 | 96,898 | [0e8a63dc14dc0945fe97148dedc8d620b4a81c5b7b989f1e3be526cede8b099e](../data/raw/0e8a63dc14dc0945fe97148dedc8d620b4a81c5b7b989f1e3be526cede8b099e.html) |
| 2026 年中秋、国庆开放安排 | 2026-11-14 19:49:51 | 6,591 | [c91e063ecf799b82442f4d4db2d858df1eb43f732bd265c2752dc262cff02fb9](../data/raw/c91e063ecf799b82442f4d4db2d858df1eb43f732bd265c2752dc262cff02fb9.html) |
| 2025 年延时开放 | 2026-11-14 19:49:53 | 6,365 | [d0e9ffd3798fe887f3c21d1d8909e080515e8e655fac6c19de2e55761c267652](../data/raw/d0e9ffd3798fe887f3c21d1d8909e080515e8e655fac6c19de2e55761c267652.html) |

| 公告 | 发布单位与发布日期 | 适用范围 | 正文位置 |
|---|---|---|---|
| [2026 年中秋、国庆开放安排](https://lib.swpu.edu.cn/1849.8080/noticex/20260915.html) | 图书馆，2026-09-15（落款和栏目日期一致） | 原文为总馆和分馆。9 月 25 日闭馆，10 月 1 日至 3 日闭馆，假期其他日期正常开放。成都一期总馆与二期分馆的对应关系可由[馆舍开放页](https://lib.swpu.edu.cn/1858.80/marx/map.html)回查。页面将南充分馆分列，本公告没有指明南充。 | `#vv_content` 第 2 段，原件第 118–121 行。落款第 129–130 行。 |
| [2025 年延时开放](https://lib.swpu.edu.cn/1849.8080/noticex/20251020.html) | 图书馆，2025-10-20（落款和栏目日期一致） | 成都校区总馆、分馆，2025-10-20 至 2025-12-20 晚间开放到 22:30。通知说明目的是满足考研同学学习需求，延长的是所列馆舍的开放时段。 | `#vv_content` 第 2 段从原件第 116 行起，日期和时间在第 117 行。落款第 124–125 行。 |
| [2026 年延时开放](https://lib.swpu.edu.cn/1849.8080/noticex/20261019.html) | 图书馆，2026-10-19 | 成都校区总馆、分馆，2026-10-19 至 2026-12-18 晚间开放到 22:30。复用[先前归档原件](../data/raw/3b8bd6329b4fab91e9ca6f3c0c8f7f87f67ebc7be12e6eb137f8489e77136eb9.html)。 | `#vv_content` 第 2 段，原件第 116 行 |

## 复跑栏目发现

在 `P:\SWPURAG` 激活 `SWPU_RAG`。下列 PowerShell 命令仅从归档首页重建选取计划。新输出的 28 条决策与本轮保存结果一致。离线重算旧招生栏目，也得到与保存计划相同的 20 条决策。额外检查确认，5 个图书馆详情 URL 的计划会被拒绝，正文 URL 位于其他主机同路径时也会被拒绝。

```powershell
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$records = Join-Path 'data/local' ('library-discovery-plan-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $records
Copy-Item samples/library-discovery/listing.json (Join-Path $records 'listing.json')
python -B -m swpurag.discover plan --column library --records $records
Get-FileHash samples/library-discovery/plan.json, (Join-Path $records 'plan.json')
```

`listing` 和 `fetch` 阶段会访问官网。实际采集复用 `swpurag.capture.capture` 保存首页，离线生成 `plan` 后才运行 `python -B -m swpurag.discover fetch --column library`。相同的阶段记录文件已存在时，入口退出并保留原记录。
