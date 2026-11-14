# 研究生招生通知首页候选与采集结果

2026-11-14 从西南石油大学研究生院招生通知首页自动发现 20 条带日期的公告，第 1 页显示共 53 条。首页于北京时间 12:30:06 返回 HTTP 200，存档 SHA-256 为 `4847df28fc359030eb2fdffd51f32b4555dc6fe1d6f57926a9c47e0bc5348b83`。解析只取公告表中带有发布日期、标题和同主机详情地址的行。先生成采前清单，再按清单各一次抓取 2 个正文 URL，均返回 HTTP 200。分页、附件、咨询外链保持登记或从原件回查。[栏目入口](https://www.swpu.edu.cn/gs/zsgz/tzgg.htm) · [首页原件](../data/raw/4847df28fc359030eb2fdffd51f32b4555dc6fe1d6f57926a9c47e0bc5348b83.html) · [20 条候选及决定](../samples/discovery/plan.json)

## 筛选和入库依据

| 采前候选 | 采集时刻（北京时间） | 发布信息及适用范围 | 正文核对及入库 |
| --- | --- | --- | --- |
| 网报温馨提示 · 8760 | 12:31:37 | 页头来源「研招办」，发布日期 2026-10-19。正文指 2027 年招生，按四川省网上报名通用提示处理。页面由西南石油大学研究生院招生办公室转载，正文未署原发布机关。 | 全部 15 个正文块纳入。第 6–7 段区分预报名流程完成与未完成，第 11 段给出首轮审核及补充材料的具体时限，第 14 段提示及时下载报名信息表。 |
| 四川网上报名相关问题解读 25 问 · 8710 | 12:31:38 | 页头来源「研招办」，发布日期 2026-10-08。标题明确为四川省 2027 年网报，导语写由「川小招」汇编，正文亦使用「我省」「我院」。入库单位记录可复核的站内发布者，即西南石油大学研究生院招生办公室（转载）。 | 问答共 59 个正文块。19、20、23、24 问涉及专项招生或加分、照顾、免初试，本轮保留完整原件并排除对应的 8 个正文块，其余 51 块纳入。第 7–11 段说明网报与网上确认一体化，第 14–16 段说明在线采集照片，第 31 段限定省内选点条件，第 51 段说明申请合理便利。 |

两份转载均标记为 `provincial_general`，适用于 2027 年四川省网上报名相关考生。旧语料仍分别记录招生单位 10615 与考点 5110 的文档角色。省内选点的一般说明保留具体考点另设条件的限定。正文的发布单位、发布日期、招生年度和适用对象分别记录，标题中的 2027 年是招生年度。[8760 官网](https://www.swpu.edu.cn/gs/info/1074/8760.htm) · [8710 官网](https://www.swpu.edu.cn/gs/info/1074/8710.htm) · [导入清单](../samples/discovery/pages.json)

| 原件 | SHA-256 | 抓取收据 |
| --- | --- | --- |
| [首页 HTML](../data/raw/4847df28fc359030eb2fdffd51f32b4555dc6fe1d6f57926a9c47e0bc5348b83.html) | `4847df28fc359030eb2fdffd51f32b4555dc6fe1d6f57926a9c47e0bc5348b83` | [首页](../samples/discovery/listing.json) |
| [8760 HTML](../data/raw/be57593c52ea086f9fb5c6861db83db73d65b99325c96168108cc9cec07989e9.html) | `be57593c52ea086f9fb5c6861db83db73d65b99325c96168108cc9cec07989e9` | [正文收据](../samples/discovery/captures.json) |
| [8710 HTML](../data/raw/add6b01932d9000c5df690cf8757d5da4e5cd2cc02928a45c8e972c664adfc73.html) | `add6b01932d9000c5df690cf8757d5da4e5cd2cc02928a45c8e972c664adfc73` | [正文收据](../samples/discovery/captures.json) |

18 条登记项包括 4 条已有样本或发布页，分别对应 10615、5110、全日制目录和非全日制目录。其余是博士、直博、导师、推免、单独考试、专项或交叉学科事项，以及考试大纲、目录预调整和直播回放。采前清单保留原始标题、URL、列表日期、原件行及排除理由。

## 重放候选筛选

在 Anaconda `SWPU_RAG` 环境中从现有首页原件重新生成清单。命令用新目录保留既有收据和筛选结果。

```powershell
Set-Location 'P:\SWPURAG'
conda activate SWPU_RAG
$env:PYTHONIOENCODING = 'utf-8'
$records = 'data/local/discovery-plan-replay'
New-Item -ItemType Directory $records | Out-Null
Copy-Item -LiteralPath samples/discovery/listing.json -Destination $records
python -B -m swpurag.discover plan --records $records
Get-FileHash -Algorithm SHA256 samples/discovery/plan.json,"$records/plan.json"
```

有新一轮采集任务时，用独立记录目录执行 `python -B -m swpurag.discover listing --records $records`，再执行 `plan`。核对 `plan.json` 中标记 `fetch` 的正文后运行 `python -B -m swpurag.discover fetch --records $records`。执行器只取首页已有的同栏目详情 URL，最多 8 条，各一次请求，间隔至少一秒，并记录失败响应。
