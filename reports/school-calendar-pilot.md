# 校级放假与调休问答试点

本轮在 `SWPU_RAG` 中从 17 篇默认库快照建立候选库，复用校级通知 44668 的归档原件。候选库为 **18 篇、821 块、32 条导入记录**，路径为 `data/local/school-calendar-pilot/candidate.sqlite3`。原 31 条导入记录逐行保留。SQLite 完整性和外键检查通过，821 个当前块均从原件重解析核对。默认库仍为 17 篇、819 块，SHA-256 为 `92f9b0e53141c0732bcb3501bac6c088eeaade7ade9ab4827beaab34892e1847`。[离线导入记录](school-calendar-import.jsonl)

## 入库范围

党政办公室（校地合作办公室）于 2026 年 9 月 11 日发布通知。已有归档收据的 SHA-256 为 `d41e34e862c3f5bc23f76635867632eff7a89bb88bcd89658a379cba251449a5`。只导入 `#vsb_content` 的第 3、4 段。两段均在 HTML 第 145 行，列号分别为 4443、7492。中秋假期为 9 月 25–27 日，国庆假期为 10 月 1–7 日，9 月 20 日和 10 月 10 日正常上班上课。具体补哪天的课程和学院例外在当前取证范围内属于缺口。[校级通知](https://www.swpu.edu.cn/info/1312/44668.htm) · [入库清单](../samples/school-calendar/pages.json) · [归档收据](../samples/school-calendar/captures.json)

校级假期和馆舍开放安排分别取证，共用 Top 5。馆舍开闭馆使用适用日期的图书馆通知，具体钟点取同馆常规表。校级安排以通知标注的假期和调休日期为准。[图书馆公告](https://lib.swpu.edu.cn/1849.8080/noticex/20260915.html)

## 冻结题与基线

S01–S08 在首次运行评测前冻结。以 `d0fd705` 的取证代码和 17 篇快照作为基线，以候选库及新取证代码作对照。两次都使用默认词法排序与共享 Top 5。冻结文件按 LF 计算的 SHA-256 为 `ad03c248158d1d42bfe6bed6acc174aedba751c9e053aa4128d8bbbe5c81edaa`。基线的校级单问进入招生路由，合问 S03 只进入图书馆路由，单独问馆舍的 S08 命中两条必要证据。[冻结题与段落标注](../samples/school-calendar/acceptance.json) · [基线 102 题逐题结果](school-calendar-before.jsonl)

在候选库中，5 道可完整回答的新题均找到全部必要证据。S05、S06 找齐了用于局部回答的校级证据，并明确说明剩余缺口。S07 无可用证据，由范围检查直接说明缺口。8 道新题均遵守主题和适用范围，错范围候选与命中均为零。原 94 题的 Top 5 排名、候选池内的必要证据、错范围评分及引用上下文一致，旧招生与图书馆回归沿用 61/62、7/7 和日期边界 4/4。H08 表头继续作为作答上下文。最终代码复跑 102 道检索，评分与记录一致。[候选库 102 题逐题结果](school-calendar-after.jsonl)

## 模型实答与浏览器

8 道新题均通过实际 `ask` 入口，7 道有证据的题调用 `deepseek-flash`。12 条引文逐条核对原文摘录、原件哈希和段落定位。问题中的 10 月 4 日同时用于校级和馆舍子问。浏览器将两部分分区显示，校级部分确认学校还在放假，馆舍部分确认成都一期已经恢复正常开放。从两张证据卡分别点开学校原件 `#L145` 与图书馆原件 `#L118`，看到了校级假期区间与馆舍开闭馆原文。实测服务已关闭。[CLI 实答与引文核验](school-calendar-ask.jsonl) · [合问终端展示](school-calendar-mixed-cli.txt)

| 冻结题 | 候选实答 | 原件位置 |
| --- | --- | --- |
| S01 中秋及国庆假期起止 | 9 月 25–27 日共 3 天，10 月 1–7 日共 7 天 | 校级通知第 3、4 段 |
| S02 两个调休上课日 | 9 月 20 日（周日）、10 月 10 日（周六）正常上课 | 校级通知第 4 段 |
| S03 10 月 4 日学校和成都一期 | 学校仍放假，成都一期正常开放 | 校级通知第 4 段、图书馆通知第 2 段 |
| S04 10 月 8 日是否仍属国庆假期 | 该日已超出公告的国庆假期区间 | 校级通知第 4 段 |
| S05 10 月 10 日及补哪天课程 | 当天正常上课，具体补哪天课程缺证据 | 校级通知第 4 段 |
| S06 计算机与软件学院例外 | 引用当天校级通用安排，说明学院有无例外缺证据 | 校级通知第 4 段 |
| S07 元旦 | 说明当前归档没有对应校级通知 | 无 |
| S08 9 月 26 日成都二期 | 正常开放，8:00 开馆 | 图书馆通知第 2 段、二期常规表第 23 段 |

对照中的主要失败是基线合问漏掉校级子问。当前试点以标点或连词识别合问，无分隔的连续问句仍可能只走一个主题。独立候选库重复导入返回 `unchanged`，正文块数仍为 821。53 项离线单元测试通过。

## 复跑命令

在 `P:\SWPURAG` 激活 `SWPU_RAG`。使用未占用的目录执行以下命令。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$work = Join-Path $PWD ('data/local/school-calendar-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$base = Join-Path $work 'before.sqlite3'
$candidate = Join-Path $work 'candidate.sqlite3'
$oldCode = Join-Path $work 'before-code'
$archives = 'samples/school-calendar'
@'
from contextlib import closing
from pathlib import Path
import sqlite3, sys
from swpurag.promotion_check import open_readonly

source = Path('data/corpus.sqlite3').resolve(strict=True)
work = Path(sys.argv[1]).resolve()
assert work.parent == Path('data/local').resolve()
work.mkdir(parents=True)
for name in ('before.sqlite3', 'candidate.sqlite3'):
    target = work / name
    target.touch(exist_ok=False)
    with closing(open_readonly(source)) as original, closing(sqlite3.connect(target)) as copy:
        original.backup(copy)
        assert copy.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not copy.execute('PRAGMA foreign_key_check').fetchall()
        assert [copy.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                for table in ('documents', 'chunks', 'attempts')] == [17, 819, 31]
    source = target
'@ | python -B - $work
if ($LASTEXITCODE -ne 0) { throw 'Snapshot failed' }
python -B -m swpurag --db $candidate import --manifest "$archives/pages.json" --captures "$archives/captures.json"
if ($LASTEXITCODE -ne 0) { throw 'Import failed' }
git archive --format=zip --output="$work/before.zip" d0fd705 swpurag
Expand-Archive -LiteralPath "$work/before.zip" -DestinationPath $oldCode
$suites = @('--boundary', '--discovery', '--expansion', '--library-discovery', 'samples/library-discovery',
            '--library-holiday', '--school-calendar', $archives)
python -B -m swpurag.routing_eval --db $base @suites --baseline-source (Join-Path $oldCode 'swpurag') --library-label-db $candidate --output "$work/before.jsonl"
python -B -m swpurag.routing_eval --db $candidate @suites --output "$work/after.jsonl"

# 在当前终端沿用项目已有模型凭据。
$env:SWPURAG_MODEL = 'deepseek-flash'
python -B -m swpurag.expansion_ask --db $candidate --library-discovery samples/library-discovery --school-calendar $archives --output "$work/ask.jsonl"
python -B -m unittest discover -s tests
python -B -m swpurag --db $candidate serve --port 8765
```

在浏览器打开 `http://127.0.0.1:8765/`，提交冻结的 10 月 4 日校级假期与成都一期开放合问。两个证据卡均可打开本地原件。完成后在服务终端按 `Ctrl+C`。
