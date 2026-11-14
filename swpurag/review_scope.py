"""Identify public registration rules and questions about individual review records."""

import re

from .store import _search_text


_REGISTRATION = re.compile(r"研招网|网报|考研|研考|报考|报名|硕士|(?:材料|资格|网报|网上)审核")
_STATUS = re.compile(r"待补充(?:材料)?|待补件|审核结果|审核结论|审核状态|审核(?:不)?通过")
_PERSONAL = re.compile(
    r"我(?:本人|个人|自己)?(?:的(?:材料|附件|审核|报名|网报|资料|页面|系统)|还?缺|漏交|还?没交|漏传)|"
    r"我个人|我本人|我的|我.{0,20}(?:显示|状态|查出|具体缺)|本人(?:的)?(?:审核|资料|材料|状态|报名)|"
    r"(?:页面|系统|材料页|审核结果|状态).{0,9}(?:显示|写着|为|是).{0,4}待补(?:充|件)"
)
_MISSING_ITEM = re.compile(
    r"(?:缺|漏交|漏传|没交|没传|(?:该|要)补)(?:了|少了|的)?(?:哪(?:一)?[份项个种]|什么)|具体(?:还)?缺|缺件"
)
_REVIEW_TIME = re.compile(
    r"(?:什么时候|几[点天]|多久|何时|多长时间).{0,10}(?:审核通过|能通过|能过|审完|出(?:审核)?结果)|"
    r"(?:审核通过|通过时间|审核).{0,8}(?:要等多久|多久|何时|什么时候|几[点天])|多久才?过"
)
_SUBMIT_DEADLINE = re.compile(
    r"(?:补充材料|补(?:交|传|材料|件)|补上材料).{0,16}(?:截止|最晚|最迟|几号前|最后期限)|"
    r"(?:截止|最晚|最迟|几号前|最后期限).{0,16}(?:补充材料|补(?:交|传|材料|件))"
)
_FIRST_REVIEW = re.compile(r"(?:首轮|第一轮|第一批).{0,12}审核.{0,16}(?:最晚|最迟|截止|完成|结束)")
_QUESTION_BREAK = re.compile(r"[。！？；!?;]+|(?=另外|此外|另问|再问|顺便问)")
_GENERIC_QUESTION = re.compile(r"[？?]|(?:多少|怎样|怎么|能不能|是否|哪些|有什么|是什么|什么时候|几号|几点)")
_SUBMISSION_QUOTE = re.compile(r"(?:显示)?[“\"「]待补充材料[”\"」]表明[^。]+。")


def review_question(question):
    """Locate an individual review question without converting a public deadline into one."""
    normalized = _search_text(question)
    if not (_REGISTRATION.search(normalized) and _STATUS.search(normalized)):
        return None
    status = bool(re.search(r"待补充(?:材料)?|待补件|审核结果|审核结论|审核状态", normalized))
    personal = bool(_PERSONAL.search(normalized) and (_MISSING_ITEM.search(normalized) or _REVIEW_TIME.search(normalized)))
    if not (status or personal):
        return None

    deadline = set()
    remainder = []
    sections = [section.strip() for section in _QUESTION_BREAK.split(question) if section.strip()]
    for section in sections:
        text = _search_text(section)
        submit = _SUBMIT_DEADLINE.search(text)
        first = _FIRST_REVIEW.search(text)
        if submit:
            deadline.add("submit")
        if first:
            deadline.add("first_review")
        if (personal and not (submit or first or _STATUS.search(text) or _MISSING_ITEM.search(text)
                              or _REVIEW_TIME.search(text)) and _GENERIC_QUESTION.search(text)):
            remainder.append(section)
    return {"status": True, "deadline": "both" if len(deadline) == 2 else next(iter(deadline), None),
            "personal": personal, "remainder": "。".join(remainder)}


def review_candidates(rows, intent):
    """Match independently citable clauses from the provincial notices."""
    provincial = [row for row in rows if row.get("role") == "provincial_general"]
    if intent["status"]:
        yield "status", [row for row in provincial if status_quote(row)
                         and "审核通过、审核不通过、待补充材料" in _search_text(row["text"])]
    if intent["deadline"]:
        yield "deadline", [row for row in provincial if all(marker in _search_text(row["text"]) for marker in
                           ("首轮报考材料审核工作", "如需提交补充材料", "完成材料提交"))]


def status_quote(row):
    match = _SUBMISSION_QUOTE.search(row["text"])
    return match[0] if match else None
