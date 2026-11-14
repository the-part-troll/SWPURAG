# 两篇四川网报资料切换至默认库

2026-11-14 在 `P:\SWPURAG` 完成切换。默认库现有 15 篇文档、15 个版本、813 个正文块、29 条导入记录。旧库原有的 27 条导入记录和其他历史数据完整保留。旧库的 SQLite 备份为 `data/local/promotion-20261114/before.sqlite3`。命令行和浏览器三类实测均通过，验收服务已关闭。[默认入口实答](default-corpus-ask.jsonl)

## 候选库切换前核验

切换前确认没有运行的 Python 演示或导入进程，8765、8766 也没有服务监听。使用 SQLite 备份 API 从默认库备份到同卷，在同一目录用备份建立候选库。只导入归档收据中的两篇文档。8760 新增 15 块，记为尝试 28；8710 新增 51 块，记为尝试 29。候选库、旧备份和验收库均通过 `PRAGMA integrity_check` 及 `PRAGMA foreign_key_check`。逐表比较旧库的所有数据行，并逐块比较验证库 813 个当前正文、来源元数据及原件出处。检索和完整性核验的连接在切换前都已关闭。[两份资料的原件和收据](discovery-candidates.md)

在候选库用默认词法与共享 Top 5 重跑 82 题，全量结果与扩库验收的必要组、错范围及完整排名位置一致。62 道可评分题中 61 道找齐。H08 的收费行仍是第 1，表头第 105 段仍作为 `rank=null` 的补充上下文。验收后以 `os.replace` 替换默认路径，随后对新默认库再次运行只读校验。48 项离线测试通过。[候选库 82 题逐题结果](default-corpus-retrieval.jsonl) · [验收参照](expansion-after.jsonl)

| 文件 | SHA-256 |
| --- | --- |
| 切换前 `data/corpus.sqlite3` | `9016183d37b02aadbde701445e557bd53ee5533e4a138e194ac23ad4d6acbcb7` |
| SQLite 备份 `data/local/promotion-20261114/before.sqlite3` | `57c4f7a4d3894c8bd95d2cf010d5741c023e6cf3de41e58d6edab5bf6919989e` |
| 切换后的 `data/corpus.sqlite3` | `df7b1fe342bd6396f6a55eaedc638da446911f0182ed7c6363bec90d06bf2a71` |

## 默认入口与浏览器实测

在 `SWPU_RAG` 中运行不带 `--db` 的 `stats`、`ask` 和 `serve --port 8765`。`stats` 显示 `8 / 15 / 15 / 813 / 29 / 0`，依次为来源、文档、版本、正文块、导入记录、失败记录。三道问题使用 `deepseek-flash`。命令行给出的五个题内引用编号均重新从归档核验。[默认命令行实答](default-corpus-ask.jsonl)

| 实测问题 | 默认 CLI | 浏览器及原件 |
| --- | --- | --- |
| N01：四川研考网报能否用相册照片，背景有什么要求 | `answered`，学信网 APP 在线拍摄，背景白色 | 两条引文指向 8710 正文块 15、16。点开本地 HTML 原件跳到 `#L200`，看到在线拍摄与白色背景的原文。两块在同一源代码行，证据卡分别显示第 10843 列与第 11393 列。 |
| 计算机与软件学院全日制 `085404` 初试第四门 | `answered`，408 计算机学科专业基础 | 引文卡显示 PDF 第 6 页、表格第 22 行。点开原件后，浏览器内置 PDF 查看器显示 `6 / 11`，链接末尾为 `#page=6`。 |
| E04：本人审核待补充，同时问公开补件时限 | `insufficient`，个人子问缺数据，公开时限子问 `answered` | 页面显示「部分已回答」，给出查看本人研招网审核意见或联系报考点的提示，另给出 10 月 31 日 12:00 前补材料的公开时限。分别引用 8710 正文块 21 与 8760 正文块 11。 |

本轮无需对默认库回滚。已在同卷临时库实演从备份恢复至 13 篇、747 块、27 条导入记录，原备份与新默认库哈希核对通过。空库两步导入也独立验证为 15 篇、813 块、15 条新导入记录。[README 离线重建](../README.md#运行方式)

## 切换命令

以下命令复用于旧默认库仍有 13 篇、747 块、27 条记录的场景。先在运行终端按 `Ctrl+C` 停演示并等待导入进程退出。用新的同卷工作目录与输出文件名。SQLite 备份与候选库都置于忽略目录，备份和候选均以独占方式创建。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$env:SWPURAG_PROMOTION_DIR = Join-Path $PWD 'data/local/promotion-repeat'
@'
from contextlib import closing
from pathlib import Path
import os, sqlite3

old = Path('data/corpus.sqlite3').resolve(strict=True)
work = Path(os.environ['SWPURAG_PROMOTION_DIR']).resolve()
assert work.parent == Path('data/local').resolve()
assert not any(old.with_name(old.name + s).exists() for s in ('-wal', '-shm', '-journal'))
work.mkdir()
assert old.stat().st_dev == work.stat().st_dev

def backup(source, target):
    target.touch(exist_ok=False)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not dst.execute('PRAGMA foreign_key_check').fetchall()
        assert [dst.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in ('documents', 'chunks', 'attempts')] == [13, 747, 27]

saved = work / 'before.sqlite3'
backup(old, saved)
backup(saved, work / 'candidate.sqlite3')
'@ | python -B -
if ($LASTEXITCODE -ne 0) { throw 'SQLite backup failed' }
$backup = Join-Path $env:SWPURAG_PROMOTION_DIR 'before.sqlite3'
$candidate = (Resolve-Path (Join-Path $env:SWPURAG_PROMOTION_DIR 'candidate.sqlite3')).Path
$results = 'reports/local/default-corpus-retrieval-repeat.jsonl'
New-Item -ItemType Directory -Force reports/local | Out-Null
python -B -m swpurag --db $candidate import --manifest P:/SWPURAG/samples/discovery/pages.json --captures P:/SWPURAG/samples/discovery/captures.json
if ($LASTEXITCODE -ne 0) { throw 'Import failed' }
python -B -m swpurag.routing_eval --db $candidate --boundary --discovery --expansion --output $results
if ($LASTEXITCODE -ne 0) { throw 'Retrieval replay failed' }
python -B -m swpurag.promotion_check --backup $backup --candidate $candidate --validation data/local/discovery.sqlite3 --results $results
if ($LASTEXITCODE -ne 0) { throw 'Candidate verification failed' }

# 以上检查通过并且连接关闭后才替换。
@'
from pathlib import Path
import os, sys
candidate = Path(sys.argv[1]).resolve(strict=True)
default = Path('data/corpus.sqlite3').resolve(strict=True)
assert candidate.name == 'candidate.sqlite3'
assert candidate.parent.parent == Path('data/local').resolve()
assert candidate.stat().st_dev == default.stat().st_dev
assert not any(p.with_name(p.name + s).exists() for p in (candidate, default) for s in ('-wal', '-shm', '-journal'))
os.replace(candidate, default)
'@ | python -B - $candidate
if ($LASTEXITCODE -ne 0) { throw 'Switch failed' }
python -B -m swpurag stats
```

## 回滚命令

停演示和导入，确认连接关闭后执行。以下命令将备份复制到同卷的临时文件，再原地替换。原备份留存，可重复用于新一轮恢复。切换后的新资料与引文未通过时使用此流程。若已在切换后执行其他导入，先单独备份当前库，再回滚以保留其历史。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
@'
from contextlib import closing
from pathlib import Path
import os, sqlite3

default = Path('data/corpus.sqlite3').resolve(strict=True)
backup = Path('data/local/promotion-20261114/before.sqlite3').resolve(strict=True)
restore = backup.with_name('restore.sqlite3')
assert backup.parent.parent == Path('data/local').resolve()
assert backup.stat().st_dev == default.stat().st_dev
assert not any(p.with_name(p.name + s).exists() for p in (backup, default) for s in ('-wal', '-shm', '-journal'))
restore.touch(exist_ok=False)
with closing(sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(restore)) as dst:
    src.backup(dst)
    assert dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    assert not dst.execute('PRAGMA foreign_key_check').fetchall()
    assert [dst.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in ('documents', 'chunks', 'attempts')] == [13, 747, 27]
os.replace(restore, default)
'@ | python -B -
if ($LASTEXITCODE -ne 0) { throw 'Restore failed' }
python -B -m swpurag stats
```
