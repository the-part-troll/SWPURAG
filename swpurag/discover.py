"""Plan and run one bounded acquisition pass for a notices homepage."""

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .capture import capture, read_archive
from .html import ERROR_TITLES, TreeParser, decode_html, elements, plain_text


YEAR = 2027


@dataclass(frozen=True)
class NoticeColumn:
    url: str
    article_prefix: str
    article_pattern: str
    records: Path
    max_details: int

    @property
    def host(self):
        return urlsplit(self.url).netloc

    def sample(self, url, prefix):
        return {"url": url, "host": self.host, "path_prefix": prefix}

    def is_article(self, url):
        value = urlsplit(url)
        return (
            value.scheme == "https" and value.netloc == self.host
            and not value.query and not value.fragment
            and re.fullmatch(self.article_pattern, value.path) is not None
        )


ADMISSIONS = NoticeColumn(
    url="https://www.swpu.edu.cn/gs/zsgz/tzgg.htm",
    article_prefix="/gs/info/1074/",
    article_pattern=r"/gs/info/1074/\d+\.htm",
    records=Path("samples/discovery"),
    max_details=8,
)
LIBRARY = NoticeColumn(
    url="https://lib.swpu.edu.cn/1849.8080/noticex/index.html",
    article_prefix="/1849.8080/noticex/",
    article_pattern=r"/1849\.8080/noticex/\d{8}\.html",
    records=Path("samples/library-discovery"),
    max_details=4,
)
COLUMNS = {"admissions": ADMISSIONS, "library": LIBRARY}
LIBRARY_TARGETS = {
    "20260915.html": "核对 2026 年中秋、国庆闭馆及恢复开放的适用日期与馆舍",
    "20251020.html": "核对 2025 年延时安排，并与已有的 2026 年同名公告按 URL 和实际日期区分",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        dump_json(stream, value)


def dump_json(stream, value):
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def listing_rows(body, charset, column=ADMISSIONS):
    tree = TreeParser()
    tree.feed(decode_html(body, charset))
    tree.close()
    nodes = list(elements(tree.root))
    title = next((plain_text(node) for node in nodes if node.tag == "title"), "")
    if "通知公告" not in title or ERROR_TITLES.search(title):
        raise ValueError("Expected a notices listing, got an invalid title")
    # 只取这一页公告表内的带日期条目，避免导航、分页和脚本中的链接扩大范围。
    if column == LIBRARY:
        # 后续分页也嵌在同一原件内，但本次发现范围限于默认显示的首页。
        pages = [node for node in nodes if node.tag == "ul" and node.attrs.get("id") == "page_ul_1"]
        if len(pages) != 1:
            raise ValueError("Expected exactly one first library notice list")
        nodes = list(elements(pages[0]))
        row_tag, link_class, date_class = "li", None, "date"
    else:
        row_tag, link_class, date_class = "tr", "c200922", "timestyle200922"
    rows = []
    seen = set()
    for row in nodes:
        if row.tag != row_tag:
            continue
        children = list(elements(row))
        links = [node for node in children if node.tag == "a"
                 and (link_class is None or node.attrs.get("class") == link_class)]
        dates = [node for node in children if node.tag == "span" and node.attrs.get("class") == date_class]
        if len(links) != 1 or len(dates) != 1:
            continue
        link = links[0]
        url = urljoin(column.url, link.attrs.get("href") or "")
        resolved = urlsplit(url)
        # 招生栏目还登记站内内容页，其地址仍不能通过正文 URL 检查。
        register_link = (
            column == ADMISSIONS and resolved.scheme == "https" and resolved.netloc == column.host
            and not resolved.fragment and resolved.path == "/gs/content.jsp"
        )
        if not (column.is_article(url) or register_link):
            continue
        if url in seen:
            continue
        seen.add(url)
        published = date(*map(int, re.split(r"[/.]", plain_text(dates[0])))).isoformat()
        rows.append({"title": plain_text(link), "url": url, "listing_date": published, "listing_line": link.line})
    if not rows:
        raise ValueError("The archived listing contained no recognizable dated notices")
    return rows


def classify(row, existing, column=ADMISSIONS):
    if row["url"] in existing:
        return "register", "已有样本原件或其发布页", existing[row["url"]]
    if column == LIBRARY:
        target = LIBRARY_TARGETS.get(urlsplit(row["url"]).path.rsplit("/", 1)[-1])
        if target:
            return "fetch", target, None
        return "register", "非本轮指定的节假日开闭馆或同名延时公告，保留登记", None
    title = row["title"]
    year = re.search(r"(20\d{2})年", title)
    if re.search(r"博士|导师|推免|免试|单独考试|专项计划|交叉学科", title):
        return "register", "博士、导师或特定招生类别，不属于本轮普通硕士范围", None
    if year and int(year[1]) < YEAR:
        return "register", "标题年度早于本轮招生年度", None
    if ("硕士研究生招生考试" in title and "网上报名" in title
            and (year and int(year[1]) == YEAR
                 or not year and row["listing_date"][:4] == str(YEAR - 1))):
        return "fetch", "网报流程或解读可能补充既有公告，正文确认发布机关、年份及新增内容后决定入库", None
    return "register", "标题不指向新的普通硕士报考、网报或确认规则", None


def make_plan(rows, manifests, column=ADMISSIONS):
    existing = {row[key]: row["id"] for manifest in manifests for row in manifest
                for key in ("url", "source_page") if row.get(key)}
    for row in rows:
        decision, reason, existing_id = classify(row, existing, column)
        row.update(decision=decision, reason=reason)
        if existing_id:
            row["existing_sample"] = existing_id
    if sum(row["decision"] == "fetch" for row in rows) > column.max_details:
        raise ValueError(f"More than {column.max_details} initial candidates require review; no details fetched")
    return rows


def detail_samples(rows, column=ADMISSIONS):
    selected = [row["url"] for row in rows if row["decision"] == "fetch"]
    if len(set(selected)) != len(selected) or len(selected) > column.max_details:
        raise ValueError(f"The approved list must contain at most {column.max_details} distinct detail URLs")
    for url in selected:
        # 不跟随重定向，也不将不在本栏目正文路径中的地址传给采集器。
        if not column.is_article(url):
            raise ValueError("The approved detail URL is outside the notice article path")
    return [column.sample(url, column.article_prefix) for url in selected]


def read_listing(data_dir, record, column=ADMISSIONS):
    receipt = read_json(record)
    if receipt.get("error") or receipt.get("http_status") != 200 or receipt.get("final_url") != column.url:
        raise ValueError("The listing request did not succeed at the declared URL")
    body = read_archive(data_dir, receipt, "html")
    return listing_rows(body, receipt.get("charset"), column)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("listing", "plan", "fetch"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--column", choices=COLUMNS, default="admissions")
    parser.add_argument("--records", type=Path, help="record directory; defaults to the selected column's records")
    parser.add_argument("--existing", type=Path, default=Path("samples/pages.json"))
    args = parser.parse_args()
    column = COLUMNS[args.column]
    records = args.records or column.records
    listing = records / "listing.json"
    plan = records / "plan.json"
    captures = records / "captures.json"
    output = {"listing": listing, "plan": plan, "fetch": captures}[args.phase]
    if output.exists():
        parser.error(f"Record already exists: {output}")
    if args.phase == "listing":
        listing.parent.mkdir(parents=True, exist_ok=True)
        with listing.open("x", encoding="utf-8", newline="\n") as stream:
            dump_json(stream, capture(column.sample(column.url, urlsplit(column.url).path), args.data_dir))
    elif args.phase == "plan":
        rows = read_listing(args.data_dir, listing, column)
        write_json(plan, make_plan(rows, [read_json(args.existing)], column))
    else:
        samples = detail_samples(read_json(plan), column)
        available = {row["url"] for row in read_listing(args.data_dir, listing, column)}
        if any(sample["url"] not in available for sample in samples):
            parser.error("A detail URL is absent from the archived listing")
        # 先占用收据文件；即使中断，也不会用同一记录路径悄悄重跑请求。
        with captures.open("x", encoding="utf-8", newline="\n") as stream:
            receipts = []
            dump_json(stream, receipts)
            stream.flush()
            for sample in samples:
                if receipts:
                    time.sleep(1)
                receipts.append(capture(sample, args.data_dir))
                stream.seek(0)
                dump_json(stream, receipts)
                stream.truncate()
                stream.flush()
    print(output)


if __name__ == "__main__":
    main()
