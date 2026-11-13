"""Identify the evidence domains explicitly addressed by a question."""

import re


_LIBRARY = re.compile(
    r"图书馆|总馆|分馆|一期(?:馆|图书馆)|二期(?:馆|图书馆)|借还|续借|借书|还书|借阅|"
    r"阅览(?:室|区)|闭馆|开馆|馆藏|明辨楼|(?:一期|二期).{0,8}(?:开放|关门|几点开)"
)
_PROGRAM = re.compile(r"(?<![a-zA-Z0-9])\d{4}[a-zA-Z0-9]{2}(?![a-zA-Z0-9])")
_ADMISSIONS = re.compile(
    r"招生|研究生考试|硕士|考研|初试|复试|研招|统考|报考|报名|报考点|推免|招生章程|"
    r"全日制|拟招|学费|同等学力|" + _PROGRAM.pattern
)
_ADMISSION_ACTION = re.compile(r"报名|报考|招生|初试|复试分数|研招|统考|拟招|学费|考哪|考什么|考点|推免")
_EXAM_SUBJECT = re.compile(r"(?:第[一二三四1234][门科]|专业课|科目).{0,8}(?:考啥|考什么|考哪|是啥|是什么)")
_DATE_PREFIX = re.compile(r"\s*(?:(?:(?:19|20)\d{2}\s*年)?\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
                          r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\s*")
_BREAK = re.compile(r"([。？！?!；;，,])|(?:另外|还有|以及|同时)(?=.{2,})")
_CLAUSE = re.compile(r"([。？！?!；;])")


def _explicit_topic(fragment, has_library, catalog_question):
    if _LIBRARY.search(fragment):
        return "library"
    if _ADMISSIONS.search(fragment) and (_ADMISSION_ACTION.search(fragment) or not has_library):
        return "admissions"
    if catalog_question and (_PROGRAM.search(fragment) or _EXAM_SUBJECT.search(fragment)):
        return "admissions"
    return None


def topic_questions(question):
    """Separate explicit cross-topic clauses and retain nearby context."""
    groups = {}
    pending = []
    last = None
    has_library = bool(_LIBRARY.search(question))
    for clause in _CLAUSE.split(question):
        # 代码和学习方式也可描述图书馆读者，须有明确的科目问法才单独路由。
        catalog_question = bool(_PROGRAM.search(clause) and "全日制" in clause and _EXAM_SUBJECT.search(clause))
        fragments = [fragment for fragment in _BREAK.split(clause) if fragment]
        labels = [_explicit_topic(fragment, has_library, catalog_question) for fragment in fragments]
        for i, (fragment, label) in enumerate(zip(fragments, labels)):
            # 逗号隔开的日期若紧跟馆舍问句，则归到该馆舍所在主题。
            next_label = next((topic for topic in labels[i + 1:] if topic), None)
            if not label and next_label == "library" and _DATE_PREFIX.fullmatch(fragment):
                label = "library"
            topic = label or last
            if topic is None:
                pending.append(fragment)
                continue
            groups.setdefault(topic, []).extend(pending + [fragment])
            pending.clear()
            last = topic
    if len(groups) > 1:
        return {topic: "".join(parts).strip("，,；;。 ") for topic, parts in groups.items()}
    topic = "library" if _LIBRARY.search(question) else "admissions"
    return {topic: question}


def interleave_hits(groups, limit):
    """Give each participating theme a slot before adding lower ranks."""
    hits = {}
    # 各主题轮流取一个结果，使共享的数量上限尽可能覆盖每个主题。
    for index in range(max(map(len, groups), default=0)):
        for group in groups:
            if index < len(group):
                row = group[index]
                hits.setdefault(row["chunk_id"], row)
                if len(hits) == limit:
                    return list(hits.values())
    return list(hits.values())
