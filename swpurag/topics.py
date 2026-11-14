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
_CALENDAR = re.compile(r"放[^。？！；，,?]{0,8}假|放(?:哪[几一]?|几)天|调休|补课|补班|教学日历")
_TEACHING = re.compile(r"上课|上班|有(?:没有)?课|没课|课表|课程|补哪天|补星期|补周几|还在假期|休假")
_HOLIDAY_QUESTION = re.compile(
    r"(?:国庆|中秋|元旦|春节|清明|劳动节|五一|端午|寒假|暑假).{0,12}"
    r"(?:怎么休|休几天|休哪几天|哪天开始休|从哪天放到哪天|休到几号|什么时候休)"
)
_DATE_TEXT = r"(?:(?:(?:19|20)\d{2}\s*年)?\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2})"
_DATE_PREFIX = re.compile(r"\s*" + _DATE_TEXT + r"\s*")
_SHARED_DAY = re.compile(_DATE_TEXT + r"|前天|昨天|昨晚|今天|今晚|今日|明天|明晚|后天")
_OWN_SCHEDULE = re.compile(r"平时|平常|常规|平日|通常|周[一二三四五六日天]|星期[一二三四五六日天]|周末")
_ASK_DATE_RANGE = re.compile(r"从哪天|哪[一两几]天|哪两个|哪天|几天|几号|从何|什么时候|起止|哪周")
_BREAK = re.compile(r"([。？！?!；;，,])|(?:另外|还有|以及|同时)(?=.{2,})|"
                    r"(?:和|那)(?=(?:成都|南充)?.{0,6}图书馆|学校.{0,8}(?:放假|调休|上课))")
_CLAUSE = re.compile(r"([。？！?!；;])")


def _explicit_topic(fragment, has_library, catalog_question, calendar_context):
    if _LIBRARY.search(fragment):
        return "library"
    if _CALENDAR.search(fragment) or _HOLIDAY_QUESTION.search(fragment):
        return "school_calendar"
    if _ADMISSIONS.search(fragment) and (_ADMISSION_ACTION.search(fragment) or not has_library):
        return "admissions"
    if catalog_question and (_PROGRAM.search(fragment) or _EXAM_SUBJECT.search(fragment)):
        return "admissions"
    if calendar_context and _TEACHING.search(fragment):
        return "school_calendar"
    return None


def _share_calendar_day(questions):
    school, library = questions.get("school_calendar"), questions.get("library")
    if not school or not library:
        return questions
    for origin, recipient in (("school_calendar", "library"), ("library", "school_calendar")):
        dates = set(_SHARED_DAY.findall(questions[origin]))
        # 只沿用另一子问的唯一日期，保留本子问自己的日期或常规时段要求。
        if (len(dates) == 1 and not _SHARED_DAY.search(questions[recipient])
                and not _OWN_SCHEDULE.search(questions[recipient])
                and not (recipient == "school_calendar" and _ASK_DATE_RANGE.search(questions[recipient]))):
            questions[recipient] = next(iter(dates)).strip() + " " + questions[recipient]
    return questions


def topic_questions(question):
    """Separate explicit cross-topic clauses and retain nearby context."""
    groups = {}
    pending = []
    last = None
    has_library = bool(_LIBRARY.search(question))
    for clause in _CLAUSE.split(question):
        # 代码和学习方式也可描述图书馆读者，须有明确的科目问法才单独路由。
        catalog_question = bool(_PROGRAM.search(clause) and "全日制" in clause and _EXAM_SUBJECT.search(clause))
        calendar_context = bool(re.search(r"学校|全校|校级|中秋|国庆|调休", clause) or _SHARED_DAY.search(clause))
        fragments = [fragment for fragment in _BREAK.split(clause) if fragment]
        labels = [_explicit_topic(fragment, has_library, catalog_question, calendar_context) for fragment in fragments]
        for i, (fragment, label) in enumerate(zip(fragments, labels)):
            # 逗号隔开的日期若紧跟馆舍问句，则归到该馆舍所在主题。
            next_label = next((topic for topic in labels[i + 1:] if topic), None)
            if not label and next_label in {"library", "school_calendar"} and _DATE_PREFIX.fullmatch(fragment):
                label = next_label
            topic = label or last
            if topic is None:
                pending.append(fragment)
                continue
            groups.setdefault(topic, []).extend(pending + [fragment])
            pending.clear()
            last = topic
    if len(groups) > 1:
        questions = {topic: "".join(parts).strip("，,；;。 ") for topic, parts in groups.items()}
        return _share_calendar_day(questions)
    topic = next(iter(groups), "admissions")
    # 保留单主题的整句。招生弱词和馆舍同时出现时沿用原有馆舍优先规则。
    if _LIBRARY.search(question):
        topic = "library"
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
