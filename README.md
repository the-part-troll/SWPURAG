# 西南石油大学官网 RAG

2026-11-12 建立。同一问答入口支持西南石油大学 **2027 年普通硕士招生**和**成都校区图书馆服务**。默认库有 **15 篇文档、813 个正文块**，包含两份四川网报资料、两份招生目录 PDF 和五份图书馆官网原件。校情、公告和教师简介可用通用检索查询。

## 环境配置

项目使用独立的 Anaconda 环境 `SWPU_RAG`，运行环境为 Python 3.12，PDF 依赖列在 [requirements-pdf.txt](requirements-pdf.txt)。在 Anaconda Prompt 进入项目根目录后配置环境。

```bat
cd /d P:\SWPURAG
conda env create -f environment.yml
conda activate SWPU_RAG
python --version
```

已有 `SWPU_RAG` 时，将创建命令换为 `conda env update -n SWPU_RAG -f environment.yml`。在 PyCharm 中选择 Conda 环境 `SWPU_RAG` 作为项目解释器。

若本机的 `conda` 启动器无法运行，可直接使用 Anaconda 下 `envs\SWPU_RAG\python.exe` 执行下方的 Python 命令。

模型读取当前进程的 `SWPURAG_API_KEY`，使用 DeepSeek 官方地址时也接受 `DEEPSEEK_API_KEY`。可选 `SWPURAG_BASE_URL` 和 `SWPURAG_MODEL`，默认是 `https://api.deepseek.com` 和 `deepseek-flash`。将密钥设在本地环境变量中，或使用[本地密钥加载示例](reports/admissions-evaluation.md)。

首次使用请先离线重建默认库，再运行下列问答示例。[重建命令](#运行方式)

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
python -B -m swpurag search "计算机与软件学院全日制085404初试考什么？" --scoped
python -B -m swpurag ask "石油与天然气工程学院非全日制085706的03油气储运工程方向初试考什么？"
python -B -m swpurag ask "2026年12月18日成都二期图书馆晚上几点关门？"
python -B -m swpurag ask "计算机与软件学院全日制085404初试第四门是什么？另外，成都总馆平时几点关门？"
```

`ask` 先识别主题。招生默认按招生年度、学习方式、学院和专业范围检索，图书馆按校区、馆舍、服务和日期过滤。复合问题分别检索和引证，共用 Top 5。有会改变答案的缺失条件时先追问。`--retriever natural` 可复现原招生自然检索。

[图书馆与跨主题评测](reports/library-evaluation.md) · [图书馆来源清单](reports/library-sources.md) · [双目录范围对照](reports/admissions-catalog-scope.md) · [招生来源清单](reports/admissions-sources.md)

## 本地浏览器演示

在项目目录激活 `SWPU_RAG`，按上方方式为当前终端配置模型。如果尚无默认库，先执行下方两条离线重建命令。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
python -B -m swpurag serve --port 8765
```

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。服务只监听本机。在启动终端按 `Ctrl+C` 停止；端口已占用时可换一个端口，并使用对应地址。

页面复用 `ask` 默认的范围检索和 Top 5 预算。点击答案中的编号可跳到对应证据，再打开官网或本地原件。HTML 存档会跳到段落起始行；PDF 会跳到文件页码，表格行号显示在证据卡上。跨主题问题分开显示回答、澄清和证据缺口。模型凭据留在服务端进程；生成时会把问题和命中的公开证据发往配置的模型服务。

[浏览器实测与命令行对照](reports/local-browser-demo.md)

词法、中文向量与 RRF 的检索对照见 [首轮混合检索报告](reports/hybrid-retrieval.md)，含冻结题、逐题排名和本地索引重建命令。浏览器仍使用现有词法检索。

常规开放、口语招生问句、续借和延期归还的修复结果见 [主题路由与证据筛选复审](reports/routing-regression.md)。

5110 考点的来源范围、退费取证和暑期归还边界见 [规则边界复审](reports/boundary-regression.md)。

从招生通知首页发现候选、归档并在独立库复测的命令与结果见 [栏目采集试验](reports/discovery-validation.md)。

15 篇独立验证库的分段适用范围、个人审核答复和前后对照见 [扩库验收报告](reports/expansion-acceptance.md)。

默认库切换、回滚及三类浏览器实测见 [默认库更新记录](reports/default-corpus-promotion.md)。

## 工作区

| 位置 | 用途 |
| --- | --- |
| `swpurag/` | 命令行、原件归档、解析与导入、基线与自然问句检索、模型回答及评测 |
| `swpurag/web/` | 本地问答页面、引文和来源展示 |
| `samples/pages.json` | 十三个明确的 URL、正文校验，以及招生、图书馆适用信息 |
| `samples/captures.json` | 实际抓取记录，包括 URL、HTTP 状态、抓取时间、原件相对路径和 SHA-256 |
| `samples/discovery/` | 两份四川网报资料的入库清单和抓取收据，以及栏目候选和验收题 |
| `data/raw/` | 官网响应的原始 HTML 和 PDF 字节。按 SHA-256 命名，Git 保留字节级换行 |
| `data/corpus.sqlite3` | 本地默认库，可从原件离线重建 |
| `tests/` | 公开样本、合成版本变更、异常正文和引用边界验证 |
| `reports/` | 来源清单、抓取命令与结果、检索和测试记录 |

## GitHub 提交范围

提交环境清单、源码、测试、样本清单、公开官网原件及供复核的评测记录。归档原件保持官网响应字节，可能含网页原有的公开联系方式。SQLite 库可以从原件重建，已排除在 Git 之外。将含个人问句、账户数据或调试输出的本地评测写到 `reports/local/`，其他私有数据放到 `data/local/`。这两个目录及本地凭据目录 `envir/` 均已忽略。提交前可用 `git status --short` 和 `git diff --cached --stat` 核对待提交文件。

## 原型借鉴

只读检查了教师目录原型的 README、依赖、抓取与检索代码、问答和 Web 入口、测试及数据目录。原型含教师 SQLite 表和照片缓存，另有一组面向清华网页的历史可达性测试。

| 原型代码 | 本轮处理 |
| --- | --- |
| `swpu_rag_crawl.py` 的链接解析、同主机限制、连接与读取超时、大小上限、离线 HTML | 沿用限定网络范围、限制请求和保留离线原件的做法。这里以清单中的精确 URL 为采集单位，同时记录主机和栏目路径 |
| `swpu_rag_crawl.py` 的正文容器、脚本排除、段落和表格处理 | 每个样本显式指定正文容器，共用解析器记录正文块和原件定位 |
| `swpu_rag.py` 的中文双字词、BM25、分段选取和编号引文，`swpu_rag_web.py` 的来源链接 | 沿用段落证据和编号展示。本轮使用确定性的子串检索，保留词法排序优化空间 |
| 机电工程学院名录路径、姓名校验、职称过滤、研究方向加权和照片定位 | 属于教师目录逻辑，本轮教师简介按普通文档入库 |
| `swpu_rag.py` 的全量删除再写入、单教师失败状态覆盖、按路径命名的快照、`swpu_rag_answer.py` 的固定模型入口 | 本轮采用 URL 文档、不可变内容版本、按哈希归档、单独记录每次尝试，命令行只输出检索证据 |

## 数据模型和版本

- `sources` 按主机名和路径前缀登记来源边界。`documents` 以来源 URL 为唯一键，记录当前版本。
- `versions` 保存标题、来源单位、页面类型、从样本确认的发布或更新日期、内容哈希、原件哈希、原件位置、响应 URL 和抓取时间。无明确日期的字段为空。
- `chunks` 保存正文块及顺序。HTML 定位包含 CSS 路径、正文块序号、原件行列，以及原文存在的锚点。行列从 1 开始，按解码后的原件字符计数。PDF 定位包含文件页码、表格行号、行坐标和单元格来源坐标，可回查同页合并格。
- `attempts` 记录每次抓取或离线导入。内容哈希基于标题、单位、类型、日期、有序正文和适用信息，原件哈希按响应字节计算。内容相同复用版本。新内容在一个数据库事务内添加版本及正文块。失败尝试与版本独立。

当前版本按校验成功的抓取时间排序，含时区时间统一比较。回放较早的快照只登记历史；较新的同内容快照推进最后成功抓取时间。检索引用仍指向版本首次入库关联的原件。`latest_success_fetched_at` 和尝试日志可用于核对当前版本的最新观察。命中正文容器后还会校验维护或登录提示、容器闭合及清单中的最低正文长度。

## 运行方式

在已激活 `SWPU_RAG` 的终端进入项目目录。首次从空库重建时，依次导入 13 份基础原件与两份四川网报归档。`import` 从随项目保留的原件读取数据。已有默认库可直接查询。离线重建会按本次执行记录导入历史，切换时保留的历史见默认库更新记录。

```powershell
Set-Location 'P:\SWPURAG'
$env:PYTHONIOENCODING = 'utf-8'
python -B -m swpurag import --manifest samples/pages.json --captures samples/captures.json
python -B -m swpurag import --manifest samples/discovery/pages.json --captures samples/discovery/captures.json
```

```powershell
python -B -m swpurag stats
python -B -m swpurag search "成都 南充 校区" --limit 1
python -B -m swpurag search "集中征集期" --limit 1 --json
python -B -m unittest discover -s tests -v
```

`search` 接受空格或标点分隔的关键词，每个词需出现在标题或同一正文块中，且至少一个词命中正文。`--json` 返回完整正文块和元数据。默认数据库为 `data/corpus.sqlite3`。可在子命令前传入 `--db <路径>` 来单独重建或检查另一份库。

复跑 13 篇、747 个正文块的旧实验时，在独立路径创建基础库。随后为 `ask`、`serve` 及评测模块显式指定这个旧库。下面是词法回归示例，向量对照的依赖和索引命令见旧实验报告。[首轮混合检索对照](reports/hybrid-retrieval.md)

```powershell
$old = 'data/local/corpus-13-replay.sqlite3'
New-Item -ItemType Directory -Force reports/local | Out-Null
python -B -m swpurag --db $old import --manifest samples/pages.json --captures samples/captures.json
python -B -m swpurag.routing_eval --boundary --db $old --output reports/local/corpus-13-regression.jsonl
```

如需重新抓取已明确列入清单的单页，可执行 `python -B -m swpurag fetch --sample overview`。每个显式 URL 发起一次请求，批量时相邻请求至少间隔一秒。重定向、访问错误、验证页或正文异常作为失败记录。采集范围、实测结果及原始抓取命令见[来源清单与样本](reports/sources.md)。

## 首轮通用文档验证

| 人工核对的问题 | 查询 | 首条原文结果 |
| --- | --- | --- |
| 学校有哪些校区？ | `成都 南充 校区` | 成都、南充，学校概况正文块 7 |
| 校史实物史料集中征集何时截止？ | `集中征集期` | 2028 年 6 月 30 日，公告正文块 42 |
| 高岳的研究方向是什么？ | `高岳 海洋工程流动安全` | 海洋工程流动安全与控制、油气储运工程，教师简介正文块 5 |
| 高岳在哪所海外大学访问？ | `高岳 纽卡斯尔大学` | 纽卡斯尔大学，教师简介正文块 13 |
| 图书馆何时闭馆？ | `图书馆 闭馆时间` | 无匹配证据，当前样本范围不含图书馆 |

真实原件重复导入后，文档、版本、正文块仍为 3、3、140，尝试日志从 3 增至 6。3 项离线测试通过，覆盖来源 URL、单位、日期和原件行列。用真实原件派生的本地合成快照验证了正文变化保留旧版、HTML 注释变化去重、历史快照回放，以及 HTTP 403、正文区域缺失和原件哈希不符时保留现有证据。合成快照仅用于测试库。[完整命令与输出](reports/verification.txt)

已核对两份带文本和表格线的目录。其他目录模板、扫描件、跨页断开的数据行、全站范围与定期采集仍待评估。
