# 成都校区图书馆与招生问答评测

2026-11-13 完成接入。两类问题共用 `ask`。图书馆覆盖成都一期总馆、二期分馆的常规开放、借阅续借及两份指定日期的临时公告。招生继续使用原年度、学院、学习方式和专业条件。混合问题分别取证和生成，在同一个 Top 5 内交替分配证据，子答复只可引用自己主题的原件。之前已有的招生条款标题等无排名上下文仍按原规则补充。

五份公开 HTML 通过 SHA-256 校验并导入，增加 99 个正文块。当时的默认库和从原件重建的隔离库均有 13 篇文档、13 个版本、747 个正文块。已验证八份原有材料重放均为原版本。[图书馆来源、原件及适用日期](library-sources.md) · [导入清单](../samples/pages.json) · [抓取清单](../samples/captures.json)

## 范围与判定

开放页原件保留三个馆舍标签，检索只导入两个成都标签。公告保留发布日期，临时适用范围另按馆舍、服务和含首尾的日期登记。暑期表按行标日期和馆舍，2026 年 7 月 20 日至 8 月 26 日只列总馆时段，分馆返回缺少相应证据。延长开放公告只用于其有效时段内的晚间开放，不证明借还窗口也延时。普通开放回答保留法定假日及另行公告条件。续借次数与时长按读者身份取证，操作途径引用读者指南。

具体日期优先使用匹配公告。明确问平时，使用常规安排。没有日期且临时安排可能改变答案时先问日期。只有月日时用北京时间当年，问“今天”或“明晚”按北京时间解释。实时座位、其他校区和未入库的临时变动属于当前样本缺口。路由识别显式的招生与图书馆词语和常见分句，同一短句省略主题的表达尚未系统评测。

## 复现命令

使用项目的 Anaconda `SWPU_RAG`（Python 3.12）和现有 PDF 解析依赖，以便同一次离线重建包含两份招生 PDF。模型评测使用 `deepseek-flash`，凭据加载沿用[招生评测配置](admissions-evaluation.md)。输出文件已存在时换名。

```powershell
Set-Location 'P:\SWPURAG'
$env:PYTHONIOENCODING = 'utf-8'
conda activate SWPU_RAG
$old = 'data/local/corpus-13-replay.sqlite3'
if (-not (Test-Path -LiteralPath $old)) { python -B -m swpurag --db $old import }
python -B -m swpurag --db $old stats
python -B -m unittest discover -s tests -v
python -B -m swpurag --db $old ask '2026年12月18日成都二期图书馆晚上几点关门？'
python -B -m swpurag.evaluate --db $old --generate --method scoped --questions samples/library-eval.json --output reports/library-evaluation-repeat.jsonl
python -B -m swpurag.evaluate --db $old --generate --method scoped --questions samples/admissions-catalog-scope-eval.json --only F3 --only F4 --only F7 --output reports/library-regression-f-repeat.jsonl
python -B -m swpurag.evaluate --db $old --generate --method scoped --only Q2 --output reports/library-regression-q-repeat.jsonl
python -B -m swpurag.evaluate --db $old --generate --method scoped --questions samples/admissions-acceptance.json --only A5 --output reports/library-regression-a-repeat.jsonl
```

## 冻结新题

2026-11-13 在模型评测前冻结八题。题集 SHA-256 为 `95a03f5be87d77629cabbe77bba3e6a70d7663b65c974123ce439335a68e3f52`。Top 5 找齐 **6/6** 道设有必要证据组的题，另有一题正确澄清和一题正确说明实时证据缺口。八题无主题误选，跨主题题各用本主题证据。所有 12 处引用通过原件复核（HTML 10、PDF 2）。[冻结问题与判据](../samples/library-eval.json) · [首次输出](library-evaluation.jsonl) · [最终逐题输出](library-evaluation-final.jsonl)

| 题目 | 必要证据排名 | 人工核对与定位 |
| --- | --- | --- |
| L1 总馆常规开放与自助借还 | 1 | 答周一至周日 8:00–22:00，周日开放期间也可自助借还，保留假日公告条件。开放页总馆段第 97 行。 |
| L2 12 月 18 日晚 22:10 二期自习 | 1 | 日期是延长公告末日，成都分馆晚间延至 22:30。公告正文第 116 行；未推断借还延时。 |
| L3 12 月 19 日分馆是否延时 | 1 | 过期公告在 Top 5 中为 0 条。首次只给常规时间、没有直接回应延时。最终给出常规 22:00，并说明现有证据无法确认该日继续延时。开放页分馆段第 202 行。模型没有逐字写出旧公告截止日。 |
| L4 研究生续借及操作 | 权限 2／指南 1 | 答研究生两次、每次 30 天，另给出两个线上渠道。借阅权限正文第 101 行对应研究生类别，成都指南第 129 行提供操作途径。 |
| L5 8 月 1 日成都图书馆几点关 | 不适用 | 先问一期还是二期，无事实主张和引文。 |
| L6 全日制 085404 与 11 月 20 日总馆晚间开放 | 招生 1／图书馆 2 | 408 和 22:30 分别引全日制目录第 6 页第 22 行、延长公告第 116 行。保留不同招生与日历时间范围。 |
| L7 当晚实时余座 | 不适用 | 明确没有该时点的实时余座数据，无数字、无引文。 |
| L8 8 月 1 日一期开放 | 1 | 只用覆盖 7 月 20 日至 8 月 26 日的总馆表格行，答 9:00–21:00。暑期公告第 133 行。 |

## 招生回归与失败样例

四道有必要证据的题均找齐，F4 继续追问。五题的必要证据组排名与图书馆入库前一致，招生证据池没有图书馆行。回归 12 处引文均回查通过（HTML 7、PDF 5）。[F3、F4、F7](library-regression-f.jsonl) · [Q2](library-regression-q.jsonl) · [A5](library-regression-a.jsonl) · [入库前对照](admissions-catalog-scope.md)

| 题目 | 必要证据排名 | 回归结果 |
| --- | --- | --- |
| F3 同院同码双目录比较 | 1、2 | 方向拟招 27 含推免、4 不含单考，两者第四门均为 801，分别引两份目录。仍漏写附带标注的拟推免 10 人。 |
| F4 085706 范围不清 | 不适用 | 追问学习方式、学院及方向，无引文。 |
| F7 085404 目录加章程 | 1、4 | 正确区分全日制初试四科与章程一般专科满两年的适用口径。 |
| Q2 普通专科与 5110 材料 | 年限 1／材料 2、3 | 保留一般专科年限和在川工作材料，仍漏写考点材料的非应届限定。 |
| A5 考点满额和总考位数 | 2 | 有据答满额处理，明确总考位数量无依据。 |

两类最终评测共 24 处引文全部通过原件复核，含 PDF 7 处。核验重新计算原件哈希、提取对应段落或表格行并匹配引文。图书馆 99 个正文块的定位也已逐块重建。27 项离线测试通过。
