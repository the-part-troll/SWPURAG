"""Identify the evidence domains explicitly addressed by a question."""

import re


_LIBRARY = re.compile(
    r"图书馆|总馆|分馆|一期(?:馆|图书馆)|二期(?:馆|图书馆)|借还|续借|借书|还书|借阅|"
    r"阅览(?:室|区)|闭馆|开馆|馆藏|明辨楼|(?:一期|二期).{0,8}(?:开放|关门|几点开)"
)
_ADMISSIONS = re.compile(
    r"招生|研究生考试|硕士|考研|初试|复试|研招|统考|报考|报名|报考点|推免|招生章程|"
    r"全日制|拟招|学费|同等学力|(?<![a-zA-Z0-9])\d{4}[a-zA-Z0-9]{2}(?![a-zA-Z0-9])"
)
_ADMISSION_ACTION = re.compile(r"报名|报考|招生|初试|复试分数|研招|统考|拟招|学费|考哪|考什么|考点|推免")
_BREAK = re.compile(r"([。？！?!；;，,])|(?:另外|还有|以及|同时)(?=.{2,})")


def topic_questions(question):
    """Separate explicit cross-topic clauses and retain nearby context."""
    groups = {}
    pending = []
    last = None
    for fragment in _BREAK.split(question):
        if not fragment:
            continue
        if _LIBRARY.search(fragment):
            topic = "library"
        # “研究生”也可能是图书馆读者身份，复合问句须有明确的招生意图才另行检索。
        elif _ADMISSIONS.search(fragment) and (_ADMISSION_ACTION.search(fragment) or not _LIBRARY.search(question)):
            topic = "admissions"
        else:
            topic = last
        if topic is None:
            # 校区、日期等先于主题出现时，等找到后续主题再一并归入。
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
