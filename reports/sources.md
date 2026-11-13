# 来源清单与样本

2026-11-12 从门户首页与站点地图浅查。分类按实际链接的主机及路径，来源单位另记。首页、站点地图会复用链接，同一菜单内也有不同单位的独立栏目。[门户首页](https://www.swpu.edu.cn/) · [站点地图](https://www.swpu.edu.cn/wzdh/zddt.htm)

## 校级入口与同主机独立栏目

以下各行主机均为 `www.swpu.edu.cn`。

| 来源范围 | 实际路径 | 本轮观察 |
| --- | --- | --- |
| 门户入口 | `/`、`/wzdh/zddt.htm` | 首页与站点地图可读，用于发现链接 |
| 校情 | `/xqzl/` | 学校概况入库。学校章程含章、条结构，已浅查。[概况](https://www.swpu.edu.cn/xqzl/xxgk.htm) · [章程](https://www.swpu.edu.cn/xqzl/xxzc.htm) |
| 机构设置 | `/jgsz/` | 学院设置列出各学院入口，作为导航来源。[学院设置](https://www.swpu.edu.cn/jgsz/xysz.htm) |
| 校级办公网与重要通知 | `/bgw.htm`、`/bgw/zytzgg.htm`、`/info/1312/` | 办公网有公开入口和通知列表。样本正文位于 `/info/1312/`，与列表路径无父子关系。[重要通知列表](https://www.swpu.edu.cn/bgw/zytzgg.htm) · [样本公告](https://www.swpu.edu.cn/info/1312/42168.htm) |
| 新闻资讯 | `/news/` | 门户要闻指向独立新闻栏目。[要闻](https://www.swpu.edu.cn/news/yw.htm) |
| 信息公开 | `/xxgk/` | 校级信息公开入口，同主机独立栏目。[信息公开](https://www.swpu.edu.cn/xxgk/xxgkw.htm) |
| 南充校区 | `/nc/` | 门户顶部单列校区入口。[南充校区](https://www.swpu.edu.cn/nc/) |
| 石油与天然气工程学院 | `/sgy/` | 院系子站。海洋油气工程教师名录下的高岳简介入库。[教师名录](https://www.swpu.edu.cn/sgy/szdw/jsml/hyyq.htm) |
| 计算机与软件学院 | `/scs/` | 院系入口跳转至同目录的 `index.jsp`。[学院入口](https://www.swpu.edu.cn/scs/) |
| 研究生院 | `/gs/zsgz/` | 招生简章列表公开，招生菜单跳到同主机的研究生院子站。[招生简章](https://www.swpu.edu.cn/gs/zsgz/zsjz.htm) |
| 教务处 | `/dean/` | 首页公开。办理缓考链接出现栏目权限提示，已停止该链接访问。[教务处](https://www.swpu.edu.cn/dean/) · [缓考链接](https://www.swpu.edu.cn/dean/detail.jsp?urltype=tree.TreeTempUrl&wbtreeid=2920) |

## 不同主机的入口

| 站点或服务 | 主机 | 导航中的路径 | 观察 |
| --- | --- | --- | --- |
| 本科生招生 | `zsb.swpu.edu.cn` | `/` | 地图 href 使用 HTTP，浅查 HTTPS 返回 412，已停止重试。[HTTPS 入口](https://zsb.swpu.edu.cn/) |
| 一网通办与信息门户 | `my.swpu.edu.cn` | `/`、`/EIP/nonlogin/homePage.htm` | 导航链接 |
| 网络理政 | `wllz.swpu.edu.cn` | `/yjfk/app/appindex` | 导航链接 |
| 电子邮件 | `mail.swpu.edu.cn` | `/` | 导航链接 |
| 图书馆学术论文投稿指南 | `lib.swpu.edu.cn` | `/1849.8080/noticex/20170515.html` | 导航链接 |
| 校友与教育发展基金会 | `xy.swpu.edu.cn` | `/` | 导航链接 |
| 就业指导 | `jyzx.swpu.edu.cn` | `/` | 导航链接 |
| 采购信息发布 | `cwcggl.swpu.edu.cn` | `/` | 导航链接 |
| 校报在线 | `xiaobao.swpu.edu.cn` | `/` | 导航链接 |
| 大学科技园、易班 | `www.swpuspark.com`、`www.yiban.cn` | `/`，易班另有 `/school/index/index?id=5349545` | 导航外链 |

标为导航链接的行只记录链接，访问状态待后续核实。两条异常均发生在来源浅查，未纳入三页样本。

## 入库样本

时间采用北京时间。抓取时间为单次公开请求开始时间。下列原件都可用 [抓取记录](../samples/captures.json) 中的完整 SHA-256 校验。

| 页面与 URL | 来源单位 | 类型及日期 | 抓取时间 | 原件与结果 |
| --- | --- | --- | --- | --- |
| [学校概况](https://www.swpu.edu.cn/xqzl/xxgk.htm) | 西南石油大学门户网站 | 学校概况，正文标注更新 2026-10-20 | 2026-11-12 14:21:20 | [HTML](../data/raw/4cdcd1519fb7323f13f044db3185d6739391b9f55a4461f684158f0600734617.html)，HTTP 200，22 块 |
| [关于迎接建校70周年校庆全面征集校史实物史料的公告](https://www.swpu.edu.cn/info/1312/42168.htm) | 档案馆 | 通知公告，页面标注发布 2026-06-16，更新日期未确认 | 2026-11-12 14:21:26 | [HTML](../data/raw/8caccdacaf4360038e71a068d7b6abc7bffbf5f4e2c2855684cbbcd0fe908d6b.html)，HTTP 200，51 块 |
| [高岳](https://www.swpu.edu.cn/sgy/szdw/jsml/hyyq/fjs/gy.htm) | 石油与天然气工程学院 | 教师简介，发布与更新日期未确认 | 2026-11-12 14:21:34 | [HTML](../data/raw/fdc3081ec997b12d9d1cfeb2ed93b2a8fcad066e1883ea7a37251914e7c36a8c.html)，HTTP 200，67 块 |

采样时，在项目根目录执行以下 PowerShell 命令，逐项调用现在供 `fetch` 使用的同一个抓取函数。保留此命令用于复核首次抓取过程，复现导入时直接使用 `python -B -m swpurag import`。

```powershell
@'
import json
import time
from pathlib import Path
from swpurag.capture import capture

manifest = json.loads(Path("samples/pages.json").read_text(encoding="utf-8"))
receipts = []
for sample in manifest:
    if receipts:
        time.sleep(1)
    receipts.append(capture(sample, Path("data")))
Path("samples/captures.json").write_text(
    json.dumps(receipts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(receipts, ensure_ascii=True, indent=2))
'@ | python -B -
```
