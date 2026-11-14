# 图书馆假期日期修订与默认库切换

2026-11-14 在 `SWPU_RAG` 中完成。默认库为 **17 篇文档、819 个正文块、31 条导入记录**，原 29 条记录及其关联数据逐行保留。切换前的 SQLite 备份为 `data/local/promotion-library-20261114/before.sqlite3`。

## 日期标注依据

校级放假通知明确中秋假期为 9 月 25–27 日、国庆假期为 10 月 1–7 日。图书馆公告引用该通知，给出成都总馆、分馆的两段闭馆安排和其余假期日期的开放安排。校级通知第 3、4 段用于划定假期，单独存档；问答的开闭馆结论引用图书馆公告第 2 段，具体钟点引用对应馆舍的常规开放表。两个假期之间的 9 月 28–30 日，以及 10 月 8 日起的日期，不由这份假期公告确认。[校级通知](https://www.swpu.edu.cn/info/1312/44668.htm) · [图书馆公告](https://lib.swpu.edu.cn/1849.8080/noticex/20260915.html) · [原件收据、段落及行列索引](../samples/library-discovery/holiday-calendar-provenance.json)

| 日期（2026 年） | 成都一期总馆、二期分馆取证范围 |
| --- | --- |
| 9 月 25 日、10 月 1–3 日 | 公告明确闭馆 |
| 9 月 26–27 日、10 月 4–7 日 | 公告确认正常开放，具体钟点取同馆常规表 |
| 9 月 28–30 日、10 月 8 日 | 当前归档仅有常规时段可参考 |

## 候选库验收与默认入口实测

从 15 篇默认库通过 SQLite 备份 API 保存旧库，再从备份创建同卷候选库。仅导入两份图书馆归档，各增加 3 块和 1 条导入记录。SQLite 完整性和外键检查通过，819 个当前块全部按修订清单从原件核对。独立空库通过 README 的三次离线导入重建为 17 篇、819 块、17 条本次导入记录，当前正文和元数据与默认库一致。50 项离线单元测试通过。[修订后的入库清单](../samples/library-discovery/pages.json) · [两份归档收据](../samples/library-discovery/captures.json)

候选库用默认词法与共享 Top 5 重跑 **90 道原题及 4 道冻结补充题**。原 90 题的排名、必要证据和错范围结果完全一致。旧题仍为 **61/62**，图书馆原题仍为 **7/7**。H08 的收费行仍排第 1，表头第 105 段仍只作为作答上下文。四道补充题 **4/4**，错范围候选及命中均为零。[冻结补充题](../samples/library-discovery/holiday-acceptance.json) · [94 题逐题检索](library-holiday-promotion-retrieval.jsonl)

切换后运行未指定 `--db` 的 `stats`、`ask` 和 `serve --port 8765`。五道 CLI 实答使用 `deepseek-flash`，9 条引文均通过原件回查。浏览器实测使用同题 J01、K03、K04，结论和证据范围与 CLI 一致。通过页面的「查看本地原件」打开假期公告并跳到 `#L118`，核对第 119、120、121 行的两段闭馆和其余日期安排。验收演示随后关闭。[默认 CLI 逐题实答](library-holiday-promotion-ask.jsonl)

| 题目 | 默认 CLI 结论与出处 | 页面实测 |
| --- | --- | --- |
| J01 · 10 月 2 日一期 | 闭馆，公告第 2 段、原件第 118 行起 | 显示闭馆，1 张公告证据卡，点开本地原件通过 |
| K01 · 9 月 27 日二期 | 正常开放，8:00 开馆，公告第 2 段和二期常规表第 23 段 | CLI 核验 |
| K02 · 9 月 28 日二期 | 当前归档没有当天适用公告，常规 8:00 开馆，二期常规表第 23 段 | CLI 核验 |
| K03 · 10 月 7 日一期 | 正常开放至 22:00，公告第 2 段和一期常规表第 1 段 | 显示正常开放至 22:00，公告和常规表各一张证据卡 |
| K04 · 10 月 8 日一期 | 当前归档没有当天适用公告，常规 22:00 闭馆，一期常规表第 1 段 | 显示归档覆盖提示，仅有常规表证据卡 |

| 数据库 | SHA-256 |
| --- | --- |
| 切换前的默认库 | `df7b1fe342bd6396f6a55eaedc638da446911f0182ed7c6363bec90d06bf2a71` |
| 旧库备份 | `7814c01c881585507fb71b226362286ef16d0f1bef5ec6f6d404d85219da0661` |
| 切换后的默认库 | `92f9b0e53141c0732bcb3501bac6c088eeaade7ade9ab4827beaab34892e1847` |

## 复跑验收和切换

以下流程用于默认库仍为 15 篇、813 块、29 条记录的环境。先在服务终端按 `Ctrl+C`，等待导入和其他项目数据库连接关闭。使用未占用的工作目录。若只复核当前 17 篇默认库，可用下方验收命令，把 `--candidate` 指向 `data/corpus.sqlite3`，`--results` 指向已保存的 94 题结果。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$work = Join-Path $PWD ('data/local/promotion-library-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$backup = Join-Path $work 'before.sqlite3'
$candidate = Join-Path $work 'candidate.sqlite3'
$results = Join-Path $work 'retrieval.jsonl'
$records = 'samples/library-discovery'
@'
from contextlib import closing
from pathlib import Path
import sqlite3, sys
from swpurag.promotion_check import open_readonly

source = Path('data/corpus.sqlite3').resolve(strict=True)
work = Path(sys.argv[1]).resolve()
assert work.parent == Path('data/local').resolve()
assert not any(source.with_name(source.name + ext).exists() for ext in ('-wal', '-shm', '-journal'))
work.mkdir()
assert work.stat().st_dev == source.stat().st_dev
for original, target in ((source, work / 'before.sqlite3'), (work / 'before.sqlite3', work / 'candidate.sqlite3')):
    target.touch(exist_ok=False)
    with closing(open_readonly(original)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not dst.execute('PRAGMA foreign_key_check').fetchall()
        assert [dst.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                for table in ('documents', 'chunks', 'attempts')] == [15, 813, 29]
'@ | python -B - $work
if ($LASTEXITCODE -ne 0) { throw 'SQLite backup failed' }
python -B -m swpurag --db $candidate import --manifest "$records/pages.json" --captures "$records/captures.json"
if ($LASTEXITCODE -ne 0) { throw 'Import failed' }
python -B -m swpurag.routing_eval --db $candidate --boundary --discovery --expansion --library-discovery $records --library-holiday --output $results
if ($LASTEXITCODE -ne 0) { throw 'Retrieval replay failed' }
python -B -m swpurag.promotion_check --library-holiday --backup $backup --candidate $candidate --results $results
if ($LASTEXITCODE -ne 0) { throw 'Candidate verification failed' }
@'
from contextlib import closing
from pathlib import Path
import os, sys
from swpurag.promotion_check import TABLES, open_readonly, rows_by_id

default = Path('data/corpus.sqlite3').resolve(strict=True)
backup, candidate = (Path(arg).resolve(strict=True) for arg in sys.argv[1:])
assert backup.name == 'before.sqlite3' and candidate.name == 'candidate.sqlite3'
assert backup.parent == candidate.parent and candidate.parent.parent == Path('data/local').resolve()
assert candidate.stat().st_dev == backup.stat().st_dev == default.stat().st_dev
assert not any(p.with_name(p.name + ext).exists() for p in (backup, candidate, default)
               for ext in ('-wal', '-shm', '-journal'))
with closing(open_readonly(default)) as current, closing(open_readonly(backup)) as saved:
    assert all(rows_by_id(current, table) == rows_by_id(saved, table) for table in TABLES)
os.replace(candidate, default)
'@ | python -B - $backup $candidate
if ($LASTEXITCODE -ne 0) { throw 'Switch failed' }
python -B -m swpurag stats
$env:SWPURAG_MODEL = 'deepseek-flash'
python -B -m swpurag.expansion_ask --library-discovery $records --library-holiday --only J01 K01 K02 K03 K04 --output (Join-Path $work 'ask.jsonl')
python -B -m swpurag serve --port 8765
```

最后两条命令使用已配置的模型凭据。浏览器打开 `http://127.0.0.1:8765/`，依次提交 [J01](../samples/library-discovery/acceptance.json)、[K03 和 K04](../samples/library-discovery/holiday-acceptance.json) 的原问句。完成后在服务终端按 `Ctrl+C`。

## 回滚

先关闭演示、导入和其他数据库连接。若切换后新增了导入记录，先单独备份当前库以留存这些记录。下列命令从旧库备份复制出同卷的临时文件，校验后原子替换。已经在独立目标上演练回滚，复原后与备份逐表一致。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
@'
from contextlib import closing
from pathlib import Path
import os, sqlite3

default = Path('data/corpus.sqlite3').resolve(strict=True)
backup = Path('data/local/promotion-library-20261114/before.sqlite3').resolve(strict=True)
restore = backup.with_name('restore.sqlite3')
assert backup.parent.parent == Path('data/local').resolve()
assert backup.stat().st_dev == default.stat().st_dev
assert not any(p.with_name(p.name + ext).exists() for p in (backup, default)
               for ext in ('-wal', '-shm', '-journal'))
restore.touch(exist_ok=False)
with closing(sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(restore)) as dst:
    src.backup(dst)
    assert dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    assert not dst.execute('PRAGMA foreign_key_check').fetchall()
    assert [dst.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
            for table in ('documents', 'chunks', 'attempts')] == [15, 813, 29]
os.replace(restore, default)
'@ | python -B -
if ($LASTEXITCODE -ne 0) { throw 'Restore failed' }
python -B -m swpurag stats
```
