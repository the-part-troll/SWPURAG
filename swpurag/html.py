"""Extract source-addressable text blocks from an explicitly selected HTML region."""

import re
from collections import Counter
from datetime import date
from html.parser import HTMLParser


VOID = set("area base br col embed hr img input link meta param source track wbr".split())
IGNORED = set("script style template noscript iframe".split())
BLOCKS = set("p li pre blockquote dt dd tr h1 h2 h3 h4 h5 h6".split())
CONTAINERS = set("article section main div td th".split())
ERROR_TITLES = re.compile(
    r"访问验证|安全验证|验证码|访问受限|访问被拒绝|没有访问|页面不存在|"
    r"access denied|just a moment|verify you are human|403 forbidden|404 not found",
    re.IGNORECASE,
)
RESPONSE_NOTICES = re.compile(
    r"^(?:(?:(?:本|该)?(?:网站|系统|页面|站点|服务)(?:当前)?(?:正在|暂时|处于)?"
    r"|正在|临时)(?:升级维护中?|维护中?|升级中)|维护中"
    r"|(?:网站|系统|服务)(?:暂不可用|暂时不可用|繁忙)"
    r"|(?:您|用户)(?:尚|还)?未登录"
    r"|(?:请(?:先)?)?登录后(?:再|才可|方可|才能)?(?:访问|查看|阅读)"
    r"(?:本(?:页面|页|内容)|正文)?"
    r"|(?:页面|内容|正文)(?:加载失败|加载中|不完整)|暂无(?:内容|正文)"
    r"|(?:website|site|system) (?:is )?under maintenance"
    r"|(?:please )?(?:log in|sign in) to (?:continue|view this (?:page|content))"
    r"|(?:page|content) (?:failed to load|is incomplete))"
    r"(?=$|[\s，。！：、；,.!?:;])",
    re.IGNORECASE,
)


class Element:
    def __init__(self, tag, attrs=(), line=0, column=0, index=1):
        self.tag = tag
        self.attrs = dict(attrs)
        self.line = line
        self.column = column
        self.index = index
        self.closed = False
        self.children = []
        self.tag_counts = Counter()


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        # HTML 允许省略段落结束标签，连续段落仍按同级节点定位。
        if tag == "p" and self.stack[-1].tag == "p":
            self.stack.pop()
        parent = self.stack[-1]
        parent.tag_counts[tag] += 1
        line, column = self.getpos()
        # 出处行列都从 1 开始，列号按解码后的字符计数。
        node = Element(tag, attrs, line, column + 1, parent.tag_counts[tag])
        parent.children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].closed = True
                del self.stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def elements(node):
    yield node
    for child in node.children:
        if isinstance(child, Element) and child.tag not in IGNORED:
            yield from elements(child)


def text_parts(node):
    for child in node.children:
        if isinstance(child, str):
            yield child
        elif child.tag == "br":
            yield "\n"
        elif child.tag not in IGNORED:
            boundary = child.tag in BLOCKS or child.tag in CONTAINERS
            if boundary:
                yield "\n"
            yield from text_parts(child)
            if boundary:
                yield "\n"


def plain_text(node):
    lines = (" ".join(line.split()) for line in "".join(text_parts(node)).split("\n"))
    return "\n".join(line for line in lines if line)


def find_region(nodes, selector):
    if not re.fullmatch(r"[#.][a-zA-Z_][a-zA-Z_0-9-]*", selector):
        raise ValueError("Body selector must be a single #id or .class")
    name = selector[1:]
    if selector.startswith("#"):
        matches = [node for node in nodes if node.attrs.get("id") == name]
    else:
        matches = [node for node in nodes if name in (node.attrs.get("class") or "").split()]
    if len(matches) != 1:
        raise ValueError("Expected one body region {}, found {}".format(selector, len(matches)))
    return matches[0]


def blocks(node, selector):
    descendants = list(elements(node))[1:]
    # 有结构的容器继续向内分块，避免把整块模板与子段落同时索引。
    is_leaf = node.tag in CONTAINERS and not any(
        child.tag in BLOCKS or child.tag in CONTAINERS for child in descendants
    )
    if node.tag in BLOCKS or is_leaf:
        text = plain_text(node)
        if text:
            yield {
                "text": text,
                "locator": {
                    "kind": "html",
                    "selector": selector,
                    "line": node.line,
                    "column": node.column,
                    "anchor": node.attrs.get("id"),
                },
            }
        return
    for child in node.children:
        if isinstance(child, Element) and child.tag not in IGNORED:
            child_selector = "{} > {}:nth-of-type({})".format(selector, child.tag, child.index)
            yield from blocks(child, child_selector)


def decode_html(body, charset):
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig")
    if not charset:
        match = re.search(br'<meta\b[^>]*\bcharset\s*=\s*["\']?([a-zA-Z0-9_-]+)',
                          body[:8192], re.IGNORECASE)
        charset = match.group(1).decode("ascii") if match else "utf-8"
    return body.decode(charset)


def validate_body(region, chunks, sample):
    # 状态码为 200 时仍可能收到半截正文、登录或维护页。
    if not region.closed and region.tag in {"div", "article", "section", "main"}:
        raise ValueError("Body region is incomplete: closing tag missing")
    if not chunks:
        raise ValueError("Body region has no text")
    first = chunks[0]["text"]
    if (ERROR_TITLES.search(first[:80])
            or any(RESPONSE_NOTICES.match(chunk["text"]) for chunk in chunks[:3])
            or re.fullmatch(r"请(?:先)?登录[。！!]?", first)):
        raise ValueError("Body region contains a maintenance, login, or incomplete-page message")
    if any(
        node.tag == "input" and (node.attrs.get("type") or "").lower() == "password"
        for node in elements(region)
    ):
        raise ValueError("Body region contains a login form")

    minimum = sample.get("minimum_body_chars", 0)
    if type(minimum) is not int or minimum < 0:
        raise ValueError("minimum_body_chars must be a nonnegative integer")
    if sum(len(re.sub(r"\s+", "", chunk["text"])) for chunk in chunks) < minimum:
        raise ValueError("Body region is shorter than the configured minimum")

    required_anchors = sample.get("required_body_anchors", [])
    if not isinstance(required_anchors, list) or any(
        not isinstance(anchor, str) or not anchor for anchor in required_anchors
    ):
        raise ValueError("required_body_anchors must be a list of nonempty strings")
    if required_anchors:
        anchors = {node.attrs.get("id") for node in elements(region)}
        anchors.update(node.attrs.get("name") for node in elements(region) if node.tag == "a")
        missing = set(required_anchors) - anchors
        if missing:
            raise ValueError("Body region is missing configured anchors: " + ", ".join(sorted(missing)))


def extract(body, charset, sample):
    tree = TreeParser()
    tree.feed(decode_html(body, charset))
    tree.close()
    nodes = list(elements(tree.root))
    browser_title = next((plain_text(node) for node in nodes if node.tag == "title"), "")
    page_title = next(
        (node.attrs.get("content") or "" for node in nodes
         if node.tag == "meta" and (node.attrs.get("name") or "").lower() == "pagetitle"),
        "",
    )
    title = (page_title or browser_title).strip()
    if (not title or ERROR_TITLES.search(browser_title + " " + title)
            or RESPONSE_NOTICES.match(browser_title) or RESPONSE_NOTICES.match(title)):
        raise ValueError("Missing title or page indicates an access or verification error")

    chunks = []
    # 同一页面的不同馆舍容器可各自带适用范围。
    sections = sample.get("body_sections") or [{"selector": sample.get("body_selector")}]
    for section in sections:
        selector = section["selector"]
        region = find_region(nodes, selector)
        extracted = list(blocks(region, selector))
        validate_body(region, extracted, section if "body_sections" in sample else sample)
        if section.get("scope"):
            for chunk in extracted:
                chunk["locator"]["library_scope"] = dict(section["scope"])
        chunks.extend(extracted)
    # 段落标记须唯一命中，避免网页变动后把馆舍或有效期贴错位置。
    for assignment in sample.get("chunk_scopes", []):
        matching = [chunk for chunk in chunks if all(
            marker in chunk["text"] for marker in assignment["contains"]
        )]
        if len(matching) != 1:
            raise ValueError("Expected one HTML block for library scope markers: " + ", ".join(assignment["contains"]))
        matching[0]["locator"].setdefault("library_scope", {}).update(assignment["scope"])
    for paragraph, chunk in enumerate(chunks, 1):
        chunk["locator"]["paragraph"] = paragraph

    dates = {}
    if sample.get("date_labels"):
        visible = plain_text(tree.root)
        for field, label in sample["date_labels"].items():
            match = re.search(
                re.escape(label) + r"\s*[：:]\s*(\d{4})(?:年|-)(\d{1,2})(?:月|-)(\d{1,2})日?",
                visible,
            )
            if match:
                dates[field] = date(*map(int, match.groups())).isoformat()
    return title, chunks, dates
