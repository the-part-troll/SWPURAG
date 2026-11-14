"""Select applicable library evidence before ranking original excerpts."""

from datetime import date, datetime, timedelta, timezone
import re

from .retrieval import rank_candidates
from .store import _search_text


_SHANGHAI = timezone(timedelta(hours=8))
_CHENGDU = "成都校区"
_MAIN = "成都总馆"
_BRANCH = "成都分馆"
_BUILDINGS = {
    _MAIN: r"总馆|一期(?:图书馆|馆)?|主馆",
    _BRANCH: r"分馆|二期(?:图书馆|馆)?|明辨楼\s*f\s*区",
}
_HOURS = re.compile(r"开馆|关馆|闭馆|关门|开放|开门|开到|自习|能进|入馆|营业|阅览")
_MACHINE = re.compile(r"(?:自动|自助)(?:借还|还书|借书)|(?:借还|还书)(?:机|仪)")
_LOANS = re.compile(r"借阅|借书|借的书|还书|续借|续期|能续|可续|借期|归还|借还|借几本|借多少本|外借|超期")
_REALTIME = re.compile(r"(?:剩|还有|空余|空闲|空着|实时|余量|有没有).{0,10}(?:座位|座席|空位)|(?:座位|座席|空位).{0,10}(?:剩|空余|余量|空着)|余座")
_REGULAR_WORDS = r"平时|平常|常规|通常|平日|普通|正常(?:情况下|开放|时间)|一般"
_REGULAR = re.compile(_REGULAR_WORDS)
_EXTENDED_HOURS = re.compile(
    r"延时|延长|延后(?:闭馆|关门)|多开(?:一会|一阵|多久|多少)|"
    rf"比(?:{_REGULAR_WORDS})(?:关得|开得|待得|更)?晚"
)
_UNRESOLVED_PERIOD = re.compile(r"暑假|暑期|寒假|寒假期间|节假日|法定假日|节日期间|这几天|最近几天|下(?:一)?周|本周")
_FULL_DATE = re.compile(r"(?<!\d)(\d{4})(?:\s*年\s*|[-/.])(\d{1,2})(?:\s*月\s*|[-/.])(\d{1,2})(?:\s*[日号])?(?!\d)")
_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
_RELATIVE = {"前天": -2, "昨天": -1, "昨晚": -1, "今天": 0, "今晚": 0, "今日": 0,
             "现在": 0, "此刻": 0, "明天": 1, "明晚": 1, "后天": 2}
_RELATIVE_DATE = re.compile("|".join(_RELATIVE))
_YEAR = re.compile(r"(?<!\d)(\d{4})\s*年(?!度)")
_HOLIDAY_RETURN = re.compile(r"寒假|暑假|暑期|假期|顺延|延期|超期|还书日")
_RETURN_CONTEXT = re.compile(r"归还|还书|超期|到期|应还|该还")
_RETURN_CASE = re.compile(r"(?:这|那)本|我的书|今年|去年|明年|(?:这|那|本)次|(?:本|下)周")
_RETURN_CHECK = re.compile(r"算(?:不算)?超期|(?:会不会|会|是否|有没有)超期")
_DEADLINE_QUESTION = re.compile(r"最迟|最晚|哪(?:天|日)|何时|什么时候|几点")
_DATE_CLAUSE = re.compile(r"[，,。；;？?!！]")
_DUE_BEFORE = re.compile(
    r"(?:原定|原本|本来|(?:原)?到期日(?:期)?|原还书日(?:期)?|归还期限|应还(?:日期?)?|该还)"
    r"\s*(?:应于|要在|该在|要|该|是|为|在|于|:)?\s*$"
)
_DUE_AFTER = re.compile(r"^\s*(?:就|才|该|应|要|需要|必须)?\s*(?:到期|应还|该还)")
_PLAN_BEFORE = re.compile(
    r"(?:打算|计划|准备|预计|预定|实际|想)(?:归还日(?:期)?|还书日(?:期)?)?\s*(?:是|为|在|于|:)?\s*$"
)
_PLAN_AFTER = re.compile(
    r"^\s*(?:那天|当天|以后|下午|上午|晚上)?\s*(?:再|才|就|去|来|能|可以)*(?:成都[总分]馆|(?:成都)?[一二]期(?:图书馆)?)?"
    r"\s*(?:归还|还(?:书|给|这本|那本|$|(?=[，。？；,.?;\s]|算|会|行|就|可以)))"
)
_UNRETURNED_AFTER = re.compile(
    r"^\s*(?:当天|当日|这天)?\s*(?:仍(?:然)?|一直|还|尚)?\s*(?:未(?:曾)?|没(?:有)?)\s*"
    r"(?:归还|还书|还(?:这本|那本|它|$))"
)
_RETURN_LIMIT = re.compile(
    r"在\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]\s*\(含(?:当)?日\)\s*(?:之?前)?\s*(?:归还|还书)"
)
_WAIVER_START = re.compile(
    r"还书日期在\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"
    r"(?:起|至)\s*[^。]*?\(均含(?:当)?日\)[^。]*?视为不超期"
)
_CARRYOVER_LIMIT = re.compile(
    r"在\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"
    r"\s*\(含(?:当)?日\)\s*(?:之?前)已经到期的未归还图书[^。]*?超期天数[^。]*?连续计算[^。]*?不会给予扣除"
)
_READER = {
    "graduate": r"研究生|硕士生|博士生",
    "undergraduate": r"本科(?:生)?",
    "external": r"校外|社会读者",
}


def _query_date(question, today):
    full = list(_FULL_DATE.finditer(question))
    # 先移除完整日期，避免同一个日期又被识别为省略年份的月日。
    remaining = _FULL_DATE.sub(" ", question)
    partial = list(_MONTH_DAY.finditer(remaining))
    relative = {_RELATIVE[word] for word in _RELATIVE if word in question}
    # “比平常晚”问的是延时，不能把用于比较的常规时段当作答案。
    regular = bool(_REGULAR.search(question) and not _EXTENDED_HOURS.search(question))
    if len(full) + len(partial) + len(relative) > 1:
        return None, None, "请指定要查询的一个具体日期。"
    try:
        if full:
            return date(*map(int, full[0].groups())).isoformat(), "explicit", None
        if partial:
            return date(today.year, *map(int, partial[0].groups())).isoformat(), "assumed_year", None
    except ValueError:
        return None, None, "请提供有效的日期。"
    if relative:
        return (today + timedelta(days=next(iter(relative)))).isoformat(), "relative", None
    if _UNRESOLVED_PERIOD.search(question):
        return None, None, "请问具体是哪一天？寒暑假和节假日的开放安排可能不同。"
    return None, "regular" if regular else None, None


def _return_date_role(before, after):
    # 「原定某日归还」的原定修饰日期，即使日期后也是还书动作。
    if _DUE_BEFORE.search(before) or _DUE_AFTER.search(after):
        return "due_date"
    if _UNRETURNED_AFTER.search(after):
        return "unreturned_on"
    if _PLAN_BEFORE.search(before) or _PLAN_AFTER.search(after):
        return "return_date"
    return None


def _loan_dates(question, today):
    mentions = [(match, "explicit") for match in _FULL_DATE.finditer(question)]
    for pattern, source in ((_MONTH_DAY, "assumed_year"), (_RELATIVE_DATE, "relative")):
        mentions.extend((match, source) for match in pattern.finditer(question)
                        if not any(start.start() <= match.start() < start.end() for start, _ in mentions))
    mentions.sort(key=lambda item: item[0].start())
    years = {int(year) for year in _YEAR.findall(question)}
    years.update(int(match[1]) for match, source in mentions if source == "explicit")
    dates = {}
    for i, (match, source) in enumerate(mentions):
        previous = mentions[i - 1][0].end() if i else 0
        following = mentions[i + 1][0].start() if i + 1 < len(mentions) else len(question)
        before = _DATE_CLAUSE.split(question[previous:match.start()])[-1]
        after = _DATE_CLAUSE.split(question[match.end():following], maxsplit=1)[0]
        role = _return_date_role(before, after)
        if not role:
            # 未被用作还书时间的“现在”等可能只是叙述时间。
            if source == "relative" and len(mentions) > 1:
                continue
            return {}, "请分别说明这本书的原到期日和计划归还日。"
        try:
            if source == "relative":
                day = today + timedelta(days=_RELATIVE[match[0]])
            elif source == "explicit":
                day = date(*map(int, match.groups()))
            else:
                if len(years) > 1:
                    return {}, "请补充原到期日和计划归还日各自的年份。"
                day = date(next(iter(years), today.year), *map(int, match.groups()))
                if years:
                    source = "context_year"
        except ValueError:
            return {}, "请提供有效的还书日期。"
        normalized = day.isoformat()
        if role in dates and dates[role] != normalized:
            label = {"due_date": "原到期日", "return_date": "计划归还日",
                     "unreturned_on": "仍未归还的日期"}[role]
            return {}, "请确认这本书的一个具体{}。".format(label)
        dates[role] = normalized
        dates[role + "_source"] = source
    if not dates.get("due_date") and (dates or years or _RETURN_CASE.search(question)):
        return dates, "请说明这本书原到期的具体日期。"
    if dates and not dates.get("return_date") and _RETURN_CHECK.search(question) and not _DEADLINE_QUESTION.search(question):
        return dates, "请说明这本书计划在哪一天归还。"
    if (dates.get("due_date", "")[5:7] == "12" and dates.get("return_date", "")[5:7] == "01"
            and {dates.get("due_date_source"), dates.get("return_date_source")}
            & {"assumed_year", "context_year"}):
        return {}, "还书可能跨年，请补充原到期日和计划归还日各自的年份。"
    return dates, None


def _notice_date(match, scope, field):
    if not match:
        return None
    year = match[1] or (scope.get(field) or "")[:4]
    try:
        return date(int(year), int(match[2]), int(match[3])).isoformat()
    except ValueError:
        return None


def _return_policy(row, row_scope, dates):
    # 用同一段原文分别识别免超期起点和超期连续计算截止，不合并两个适用条件。
    due = dates["due_date"]
    waiver = carryover = None
    for sentence in re.split(r"(?<=。)", row["text"]):
        normalized = _search_text(sentence)
        waived_from = _notice_date(_WAIVER_START.search(normalized), row_scope, "effective_from")
        carryover_through = _notice_date(_CARRYOVER_LIMIT.search(normalized), row_scope, "effective_from")
        if waived_from == due:
            waiver = sentence.strip()
        if carryover_through:
            carryover = (carryover_through, sentence.strip())
    if not carryover:
        return None
    through, quote = carryover
    if waiver and due == through and _active(row_scope, due):
        return {"kind": "overlap", "chunk_id": row["chunk_id"], "quotes": [waiver, quote]}
    observed = dates.get("unreturned_on")
    if observed and due < through <= observed and _active(row_scope, observed):
        return {"kind": "carryover", "chunk_id": row["chunk_id"], "quotes": [quote]}
    return None


def _scope(row):
    # 文档标记的是总体范围，时刻表行可能另有更窄的馆舍或适用日期。
    fields = ("campus", "building", "notice_kind", "effective_from", "effective_to", "service")
    return dict({key: row.get(key) for key in fields}, **row["locator"].get("library_scope", {}))


def _covers(scope, building):
    value = scope.get("building") or ""
    return building in re.split(r"[、，,]", value)


def _active(scope, day):
    start, end = scope.get("effective_from"), scope.get("effective_to")
    return bool(day and start and end and start <= day <= end)


def _hours_rows(rows, building, day):
    eligible = [(row, sc) for row, sc in rows if _covers(sc, building)]
    regular = [row for row, sc in eligible if sc["service"] == "hours" and sc["notice_kind"] == "regular"]
    temporary = [row for row, sc in eligible if sc["service"] == "hours"
                 and sc["notice_kind"] == "temporary" and _active(sc, day)]
    if temporary:
        return temporary, regular, "temporary"

    # 总体公告覆盖某馆、当日表格却未列该馆时，保留缺口，避免套用常规时间。
    schedule_documents = {row["document_id"] for row, sc in rows
                          if sc["service"] == "hours" and sc["notice_kind"] == "temporary"}
    covered_by_notice = any(row["document_id"] in schedule_documents and _covers(row, building)
                            and _active(row, day) for row, _ in rows)
    return ([], [], "temporary") if covered_by_notice else (regular, [], "regular")


def _loan_aspects(question):
    aspects = []
    if _RETURN_CONTEXT.search(question) and _HOLIDAY_RETURN.search(question):
        aspects.append("holiday_return")
    if re.search(r"复印", question):
        aspects.append("copy_return")
    if re.search(r"操作|如何|怎么|怎样|哪里|哪儿|去哪|在哪|到哪|平台|线上|办理|流程|入口", question):
        aspects.append("renewal_method")
    rule = re.search(r"几次|多久|多长|多少|借期|本数|上限|借阅权限|续[^，。；？！,.;?!]{0,10}几[回遍]", question)
    # 同时问次数和操作时两类都取证，次数条款在筛选时按读者身份选择。
    if not aspects or rule:
        aspects.append("renewal_rule")
    return aspects


def search_library(store, question, limit=5, today=None, *, ranker=None, trace=None):
    """Return evidence and the resolved campus, building, date, and services."""
    if limit < 1:
        raise ValueError("Search limit must be positive")
    question = _search_text(question).strip()
    today = today or datetime.now(_SHANGHAI).date()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    day, date_source, date_error = _query_date(question, today)
    buildings = [name for name, pattern in _BUILDINGS.items() if re.search(pattern, question)]
    machine = bool(_MACHINE.search(question))
    # 自助借还设备的可用时间与读者借期、续借次数分别取证。
    holiday_return = bool(_RETURN_CONTEXT.search(question) and _HOLIDAY_RETURN.search(question))
    loan_question = holiday_return or bool(_LOANS.search(_MACHINE.sub("", question)))
    realtime = bool(_REALTIME.search(question))
    # 还书问句中的「几点」本身不表示询问开放时间。
    reading_hours = bool(_HOURS.search(question) or (not holiday_return and "几点" in question)) and not realtime
    hours = machine or reading_hours
    services = (["hours"] if hours else []) + (["loans"] if loan_question else [])
    reader = [name for name, pattern in _READER.items() if re.search(pattern, question)]
    scope = {
        "topic": "library", "campus": _CHENGDU if "成都" in question or buildings else None,
        "building": "、".join(buildings) or None, "date": day, "date_source": date_source,
        "services": services, "reader_group": reader[0] if len(reader) == 1 else None,
        "notice_kind": None, "clarification": None, "unsupported": [],
    }
    gaps = scope["unsupported"]
    if re.search(r"南充|南校区", question):
        scope.update(campus="南充校区", building="南充分馆" if "馆" in question else None)
        gaps.append("当前资料未收录南充校区的适用图书馆证据。")
        return [], scope
    if realtime:
        gaps.append("现有公开存档没有该时点的实时剩余座位信息。")
    if not services:
        if not gaps:
            gaps.append("现有资料未覆盖所问的图书馆服务。")
        return [], scope

    rows = [(row, _scope(row)) for row in store.current_chunks(topic="library")]
    rows = [(row, sc) for row, sc in rows if sc["campus"] == _CHENGDU]
    if hours and not buildings:
        if scope["campus"]:
            scope["clarification"] = "请问要查询成都一期总馆，还是二期分馆？"
        else:
            scope["clarification"] = "请问要查询哪个校区、哪个馆舍？成都校区有一期总馆和二期分馆。"
        return [], scope
    if date_error and hours:
        scope["clarification"] = date_error
        return [], scope
    if hours and not day and date_source != "regular" and any(
        sc["service"] == "hours" and sc["notice_kind"] == "temporary"
        and any(_covers(sc, name) for name in buildings) for _, sc in rows
    ):
        scope["clarification"] = "请问想查询哪一天，还是只想了解常规开放时间？"
        return [], scope

    groups = []
    for building in buildings if hours else ():
        primary, regular, kind = _hours_rows(rows, building, day)
        scope["notice_kind"] = kind
        if kind == "regular" and day and _EXTENDED_HOURS.search(question):
            scope["no_applicable_extension"] = True
        machine_supported = kind == "regular" and any(_MACHINE.search(row["text"]) for row in primary)
        if primary and (reading_hours or machine_supported):
            groups.append(rank_candidates(store, question, 1, rows=primary, ranker=ranker,
                                          trace=trace, topic="library", stage="hours", fallback=True))
        if not primary and reading_hours:
            gaps.append("现有资料没有{}在所问日期适用的开放时间。".format(building))
        # 晚间延时只调整截止时间。兼问几点开馆时，才补充常规开馆资料。
        evening_only = primary and all(_scope(row).get("hours_aspect") == "evening_only" for row in primary)
        if evening_only and re.search(r"开馆|开门|几点(?:开|能进)", question):
            groups.append(rank_candidates(store, question, 1, rows=regular, ranker=ranker,
                                          trace=trace, topic="library", stage="regular_opening", fallback=True))
        if machine and not machine_supported:
            gaps.append("现有资料无法确认{}在所问时段的自助借还安排。".format(building))

    if loan_question:
        aspects = _loan_aspects(question)
        for aspect in aspects:
            applicable = [(row, sc) for row, sc in rows if sc.get("loan_aspect") == aspect
                          and sc["service"] == "loans"
                          and (not buildings or any(_covers(sc, name) for name in buildings))]
            if aspect == "renewal_rule" and len(reader) != 1:
                scope["clarification"] = "请问读者属于哪一类，例如本科生、研究生或校外读者？"
                continue
            service_day = day
            return_policies = {}
            if aspect == "holiday_return":
                loan_dates, clarification = _loan_dates(question, today)
                scope["loan_dates"] = loan_dates
                service_day = loan_dates.get("due_date")
                if not hours:
                    scope.update(date=service_day, date_source=loan_dates.get("due_date_source"))
                if service_day:
                    for row, sc in applicable:
                        if sc["notice_kind"] == "temporary":
                            return_policy = _return_policy(row, sc, loan_dates)
                            if return_policy:
                                return_policies[row["chunk_id"]] = return_policy
                # 明确的原到期日已落在公告重叠边界时，补归还日也无法消除原文歧义。
                overlap = any(policy["kind"] == "overlap" for policy in return_policies.values())
                if clarification and not overlap:
                    scope["clarification"] = clarification
                    continue
            temporary = [row for row, sc in applicable if sc["notice_kind"] == "temporary"
                         and (_active(sc, service_day) or row["chunk_id"] in return_policies)]
            policy = [row for row, sc in applicable if sc["notice_kind"] == "policy"
                      and sc.get("reader_group") in (None, scope["reader_group"])]
            # 生效的临时安排仅覆盖当前借阅事项，其他事项仍各自查找规则。
            selected = temporary or policy
            if aspect == "holiday_return" and service_day and not temporary:
                gaps.append("现有归档无适用于该原到期日的延期通知，无法按该通知判断是否超期。")
                continue
            if selected:
                ranked = rank_candidates(store, question, 1, rows=selected, ranker=ranker,
                                         trace=trace, topic="library", stage="loan:" + aspect, fallback=True)
                groups.append(ranked)
                if aspect == "holiday_return" and temporary and ranked:
                    selected_row = ranked[0]
                    return_policy = return_policies.get(selected_row["chunk_id"])
                    # 公告中的归还截止，与借阅规则本身是否适用分别判断。
                    deadline = _notice_date(_RETURN_LIMIT.search(_search_text(selected_row["text"])),
                                            _scope(selected_row), "effective_to")
                    planned = loan_dates.get("return_date")
                    loan_dates.update(extension_until=deadline,
                                      within_extension=planned <= deadline if planned and deadline and not return_policy else None)
                    if return_policy:
                        scope["return_policy"] = return_policy
            else:
                gaps.append("现有资料没有适用于所问读者、馆舍或日期的借阅证据。")
        scope["campus"] = scope["campus"] or _CHENGDU

    hits = {}
    for group in groups:
        for row in group:
            hits.setdefault((row["version_id"], row["chunk_id"]), row)
    return list(hits.values())[:limit], scope
