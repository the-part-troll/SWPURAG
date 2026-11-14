"""Plan and run one bounded acquisition pass for the graduate notices homepage."""

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .capture import capture, read_archive
from .html import ERROR_TITLES, TreeParser, decode_html, elements, plain_text


COLUMN = "https://www.swpu.edu.cn/gs/zsgz/tzgg.htm"
HOST = "www.swpu.edu.cn"
MAX_DETAILS = 8
YEAR = 2027


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        dump_json(stream, value)


def dump_json(stream, value):
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def listing_rows(body, charset):
    tree = TreeParser()
    tree.feed(decode_html(body, charset))
    tree.close()
    nodes = list(elements(tree.root))
    title = next((plain_text(node) for node in nodes if node.tag == "title"), "")
    if "通知公告" not in title or ERROR_TITLES.search(title):
        raise ValueError("Expected the graduate notices listing, got an invalid title")
    rows = []
    seen = set()
    # 只取这一页公告表内的带日期条目，避免导航、分页和脚本中的链接扩大范围。
    for row in nodes:
        if row.tag != "tr":
            continue
        children = list(elements(row))
        links = [node for node in children if node.tag == "a" and node.attrs.get("class") == "c200922"]
        dates = [node for node in children if node.tag == "span" and node.attrs.get("class") == "timestyle200922"]
        if len(links) != 1 or len(dates) != 1:
            continue
        link = links[0]
        url = urljoin(COLUMN, link.attrs.get("href") or "")
        resolved = urlsplit(url)
        if (resolved.scheme != "https" or resolved.netloc != HOST or resolved.fragment
                or not (re.fullmatch(r"/gs/info/1074/\d+\.htm", resolved.path)
                        or resolved.path == "/gs/content.jsp")):
            continue
        if url in seen:
            continue
        seen.add(url)
        published = date(*map(int, plain_text(dates[0]).split("/"))).isoformat()
        rows.append({"title": plain_text(link), "url": url, "listing_date": published, "listing_line": link.line})
    if not rows:
        raise ValueError("The archived listing contained no recognizable dated notices")
    return rows


def classify(row, existing):
    title = row["title"]
    year = re.search(r"(20\d{2})年", title)
    if row["url"] in existing:
        return "register", "已有样本原件或其发布页", existing[row["url"]]
    if re.search(r"博士|导师|推免|免试|单独考试|专项计划|交叉学科", title):
        return "register", "博士、导师或特定招生类别，不属于本轮普通硕士范围", None
    if year and int(year[1]) < YEAR:
        return "register", "标题年度早于本轮招生年度", None
    if ("硕士研究生招生考试" in title and "网上报名" in title
            and (year and int(year[1]) == YEAR
                 or not year and row["listing_date"][:4] == str(YEAR - 1))):
        return "fetch", "网报流程或解读可能补充既有公告，正文确认发布机关、年份及新增内容后决定入库", None
    return "register", "标题不指向新的普通硕士报考、网报或确认规则", None


def make_plan(rows, manifests):
    existing = {row[key]: row["id"] for manifest in manifests for row in manifest
                for key in ("url", "source_page") if row.get(key)}
    for row in rows:
        decision, reason, existing_id = classify(row, existing)
        row.update(decision=decision, reason=reason)
        if existing_id:
            row["existing_sample"] = existing_id
    if sum(row["decision"] == "fetch" for row in rows) > MAX_DETAILS:
        raise ValueError("More than eight initial candidates require review; no details fetched")
    return rows


def detail_samples(rows):
    selected = [row["url"] for row in rows if row["decision"] == "fetch"]
    if len(set(selected)) != len(selected) or len(selected) > MAX_DETAILS:
        raise ValueError("The approved list must contain at most eight distinct detail URLs")
    for url in selected:
        # 不跟随重定向，也不将不在本栏目正文路径中的地址传给采集器。
        if not re.fullmatch(r"https://www\.swpu\.edu\.cn/gs/info/1074/\d+\.htm", url):
            raise ValueError("The approved detail URL is outside the graduate notice article path")
    return [{"url": url, "host": HOST, "path_prefix": "/gs/info/1074/"} for url in selected]


def read_listing(data_dir, record):
    receipt = read_json(record)
    if receipt.get("error") or receipt.get("http_status") != 200 or receipt.get("final_url") != COLUMN:
        raise ValueError("The listing request did not succeed at the declared URL")
    body = read_archive(data_dir, receipt, "html")
    return listing_rows(body, receipt.get("charset"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("listing", "plan", "fetch"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--records", type=Path, default=Path("samples/discovery"))
    parser.add_argument("--existing", type=Path, default=Path("samples/pages.json"))
    args = parser.parse_args()
    listing = args.records / "listing.json"
    plan = args.records / "plan.json"
    captures = args.records / "captures.json"
    output = {"listing": listing, "plan": plan, "fetch": captures}[args.phase]
    if output.exists():
        parser.error(f"Record already exists: {output}")
    if args.phase == "listing":
        listing.parent.mkdir(parents=True, exist_ok=True)
        with listing.open("x", encoding="utf-8", newline="\n") as stream:
            dump_json(stream, capture({"url": COLUMN, "host": HOST, "path_prefix": "/gs/zsgz/tzgg.htm"}, args.data_dir))
    elif args.phase == "plan":
        write_json(plan, make_plan(read_listing(args.data_dir, listing), [read_json(args.existing)]))
    else:
        samples = detail_samples(read_json(plan))
        available = {row["url"] for row in read_listing(args.data_dir, listing)}
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
