# 图书馆通知栏目采集试点

本报告保留初次试点的日期标注和实验结果。复现初次试点请使用提交 `55c6c51` 的代码和清单。按校级放假通知校正后的范围、补充题及默认库切换见 [图书馆假期日期修订与切换](library-holiday-promotion.md)。

2026-11-14 在 Anaconda `SWPU_RAG` 中对照。基线从默认库做 SQLite 只读备份，候选库增量导入两份公告。本轮交付候选库及复跑记录，默认库仍为 15 篇、813 块、29 条导入记录。其 SHA-256 为 `df7b1fe342bd6396f6a55eaedc638da446911f0182ed7c6363bec90d06bf2a71`，采集和评测前后相同。[栏目发现与实际抓取记录](library-discovery-candidates.md) · [入库清单](../samples/library-discovery/pages.json)

## 采集与离线验证

采集器访问一次栏目首页。先落盘 28 条候选及筛选理由，再访问两条正文。三个请求均在原地址返回 HTTP 200。2026 年同名延时公告已在基础库中，使用已有归档。本轮补入 2026 年中秋国庆开闭馆通知和 2025 年延时开放通知。假期公告第 2 段保留原文及同一出处，并分别标记 9 月 25 日和 10 月 1–3 日闭馆。两段假期间的 9 月 26–30 日和国庆闭馆结束后的 10 月 4 日用于核验恢复常规；后续日期独立查找同日适用通知。2025 延时适用于 10 月 20 日至 12 月 20 日，2026 同名公告适用于 10 月 19 日至 12 月 18 日。馆舍对应关系从官网开放时间页核对，南充分馆单独列出。[节假日公告](https://lib.swpu.edu.cn/1849.8080/noticex/20260915.html) · [2025 年延时](https://lib.swpu.edu.cn/1849.8080/noticex/20251020.html) · [2026 年延时](https://lib.swpu.edu.cn/1849.8080/noticex/20261019.html) · [开放时间](https://lib.swpu.edu.cn/1858.80/marx/map.html)

| 阶段 | 来源 | 文档 | 版本 | 正文块 | 导入记录 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 默认库快照 | 8 | 15 | 15 | 813 | 29 |
| 两份归档首次导入 | 8 | 17 | 17 | 819 | 31 |
| 离线重复导入 | 8 | 17 | 17 | 819 | 33 |

原来的来源、文档、版本、正文块及导入记录逐行一致。两份新增原件各 3 块，均在离线重放时返回 `unchanged`。在候选库的临时副本上，对每份公告分别模拟 HTTP 403 及 HTTP 200 但正文容器缺失。四次均记录失败并保留原版本及正文块。正式候选库没有这些合成尝试。SQLite 完整性和外键检查通过。[导入、重放与故障验证逐条结果](library-discovery-import.jsonl)

## 复跑命令

从 `P:\SWPURAG` 执行。采集记录复用当前已归档文件，离线重放的栏目计划见 [采集报告](library-discovery-candidates.md#复跑栏目发现)。复跑使用空闲的候选库和输出路径。

```powershell
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$records = 'samples/library-discovery'
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
$base = "data/local/library-pilot-base-$run.sqlite3"
$candidate = "data/local/library-pilot-candidate-$run.sqlite3"
$before = "data/local/library-pilot-before-$run"
$output = "reports/local/library-pilot-$run"
New-Item -ItemType Directory -Force -Path 'data/local', 'reports/local' | Out-Null
New-Item -ItemType Directory -Path $before
New-Item -ItemType Directory -Path $output
git archive --format=zip --output="$before/code.zip" 56cf0cf swpurag
Expand-Archive -LiteralPath (Join-Path $before 'code.zip') -DestinationPath $before
@'
from contextlib import closing
from pathlib import Path
import sqlite3, sys

source = Path('data/corpus.sqlite3').resolve(strict=True)
target = Path(sys.argv[1])
target.touch(exist_ok=False)
with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original, closing(sqlite3.connect(target)) as copy:
    original.backup(copy)
    assert copy.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    assert [copy.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('documents', 'chunks', 'attempts')] == [15, 813, 29]
'@ | python -B - $base
python -B -m swpurag.discovery_import --snapshot $base --records $records --db $candidate --output "$output/import.jsonl"
python -B -m swpurag.routing_eval --db $base --baseline-source (Join-Path $before 'swpurag') --boundary --discovery --expansion --library-discovery $records --library-label-db $candidate --output "$output/before.jsonl"
python -B -m swpurag.routing_eval --db $candidate --boundary --discovery --expansion --library-discovery $records --output "$output/after.jsonl"

# 沿用本地模型凭据，外部模型调用只在实答命令发生。
$env:SWPURAG_MODEL = 'deepseek-flash'
python -B -m swpurag.expansion_ask --db $base --baseline-package $before --library-discovery $records --output "$output/ask-before.jsonl"
python -B -m swpurag.expansion_ask --db $candidate --library-discovery $records --output "$output/ask-after.jsonl"
python -B -m unittest discover -s tests -v
```

## 检索对照

J01–J08 在运行检索和问答前冻结，LF 口径 SHA-256 为 `78c3b5c65aece48912f306b7236f5679b4dbf0149f3ac293f94f01d5b4daaab4`。两次检索都用默认词法和共享 Top 5。基线使用 `56cf0cf` 的排序、范围与问答代码。新题的必要证据组以候选库和归档校验，基线缺少原件时记为 `not_in_corpus`。7 道可评分新题找齐证据从 2/7 到 7/7，三道命中错范围的题降到零。J06 的南充缺口两次均正确排除成都证据，单列统计。[冻结题](../samples/library-discovery/acceptance.json) · [基线 90 题](library-discovery-before.jsonl) · [候选 90 题](library-discovery-after.jsonl)

原 82 题复跑时显式加载图书馆的 `pages.json` 和 `captures.json`，并加载原四川资料清单。与上轮默认库记录逐题比较，必要证据排名组、错范围排名、检索状态及主题状态均一致。62 道可评分题仍为 61/62，20 道澄清和证据不足等题保留原判据。H08 的收费行排第 1，原评分仍缺第 105 段表头。表头继续以 `rank=null` 提供给模型，在该题中编号为 7。候选 90 题所有 Top 5 返回项均由归档重解析核对。[上轮默认库逐题记录](default-corpus-retrieval.jsonl)

## 逐题实答

两边均通过实际 `swpurag ask --json` 运行。候选最终复跑 7 道可答题均由 `deepseek-flash` 回答，J06 由范围检查直接给出缺口。10 条引文均逐字回查，官网地址、原件哈希、HTML 段落与查询条件一致。[基线实答](library-discovery-ask-before.jsonl) · [候选首跑](library-discovery-ask-after.jsonl) · [候选最终实答](library-discovery-ask-final.jsonl)

| 题目 | 基线实答及缺口 | 候选的结论和出处 |
| --- | --- | --- |
| J01 · 10 月 2 日成都一期 | 库内只有常规时间，模型输出被引文校验拒收 | 闭馆。节假日公告第 2 段，原件 118 行起。 |
| J02 · 10 月 4 日成都总馆 | 只有常规时段，未核实当天恢复开放 | 恢复开放，常规时段 8:00–22:00。节假日公告第 2 段、开放页第 1 段。 |
| J03 · 9 月 25 日成都二期 | 用常规表和库内无法确认的法定节日判断得出闭馆 | 闭馆一天。节假日公告第 2 段的中秋条款。 |
| J04 · 2025 年 11 月 10 日晚成都二期 | 缺少 2025 年公告，模型输出被引文校验拒收 | 22:15 仍在晚间开放时段，延长至 22:30。2025 延时公告第 2 段。 |
| J05 · 2026 年 11 月 10 日晚成都二期 | 正确命中 2026 年公告 | 22:15 仍在晚间开放时段，延长至 22:30。2026 延时公告第 2 段。 |
| J06 · 10 月 2 日南充 | 说明缺少南充校区当天证据 | 同样说明证据缺口，无成都证据混入。 |
| J07 · 10 月 16 日成都一期 | 把常规 22:00 推断为当天确定的闭馆时间 | 开放页第 1 段，常规闭馆时间为 22:00。详见下方复测。 |
| J08 · 9 月 26 日成都二期 | 只给出常规表，无法确定假期当天开放 | 正常开放，常规 8:00 开馆。节假日公告第 2 段、开放页第 23 段。 |

来源段落对应 `#vv_content` 的节假日第 2 段（原件 118 行起），两份延时公告各自的第 2 段（原件 116 行起），开放时间页第 1 段（97 行）和第 23 段（202 行）。节假日公告仅写总馆、分馆。成都一期和二期的映射来自开放时间页。当前档案没有证据确认南充分馆在节假日问句所涉日期的安排。仅在试点已归档日期范围内优先使用临时公告；其他日期的常规表不能证明当天实际开闭馆。[原件索引和适用范围](library-discovery-candidates.md#采集及原件核对)

J07 首跑已检出一期常规表，回答仍因事实项缺少可验证引文而被拒收。第一次修订后通过引文校验，但同一条回答又把常规 22:00 说成当天确定关门，仍未达验收判据。最终把归档覆盖说明独立输出为 `scope_note`，仅有常规表的纯开放时段问题在传给模型时去除指定日期。最终实答明确当日缺少适用临时安排，只引用常规 22:00。候选最终版再次复跑 90 道检索题，除耗时外与候选首跑记录一致。[J07 中间复测](library-discovery-ask-retest.jsonl) · [最终实答原件核对](library-discovery-ask-final.jsonl)

50 项离线单元测试通过。仍有 H08 的原 Top 5 表头漏证。南充目前只能说明归档缺口；成都与南充合问馆舍时，现有范围判断会先返回南充缺口。本轮实答核验按两个校区分别提问。
