"""Select applicable library evidence before ranking original excerpts."""

from datetime import date, datetime, timedelta, timezone
import re

from .retrieval import search_natural
from .store import _search_text


_SHANGHAI = timezone(timedelta(hours=8))
_CHENGDU = "成都校区"
_MAIN = "成都总馆"
_BRANCH = "成都分馆"
_BUILDINGS = {
    _MAIN: r"总馆|一期(?:图书馆|馆)?|主馆",
    _BRANCH: r"分馆|二期(?:图书馆|馆)?|明辨楼\s*f\s*区",
}
_HOURS = re.compile(r"几点|开馆|关馆|闭馆|关门|开放|开门|开到|自习|能进|能进去|入馆|营业|阅览")
_MACHINE = re.compile(r"(?:自动|自助)(?:借还|还书|借书)|(?:借还|还书)(?:机|仪)")
_LOANS = re.compile(r"借阅|借书|借的书|还书|续借|续期|能续|可续|借期|归还|借还|借几本|借多少本|外借|超期")
_REALTIME = re.compile(r"(?:剩|还有|空余|空闲|空着|实时|余量|有没有).{0,10}(?:座位|座席|空位)|(?:座位|座席|空位).{0,10}(?:剩|空余|余量|空着)|余座")
_REGULAR = re.compile(r"平时|常规|通常|平日|普通|正常(?:情况下|开放|时间)|一般")
_UNRESOLVED_PERIOD = re.compile(r"暑假|暑期|寒假|寒假期间|节假日|法定假日|节日期间|这几天|最近几天|下(?:一)?周|本周")
_FULL_DATE = re.compile(r"(?<!\d)(\d{4})(?:\s*年\s*|[-/.])(\d{1,2})(?:\s*月\s*|[-/.])(\d{1,2})(?:\s*[日号])?(?!\d)")
_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
_RELATIVE = {"前天": -2, "昨天": -1, "昨晚": -1, "今天": 0, "今晚": 0, "今日": 0,
             "现在": 0, "此刻": 0, "明天": 1, "明晚": 1, "后天": 2}
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
    regular = bool(_REGULAR.search(question))
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


def _rank(store, question, rows, limit):
    if not rows:
        return []
    ranked = search_natural(store, question, limit, rows=rows)
    combined = {}
    for row in ranked + rows:
        combined.setdefault((row["version_id"], row["chunk_id"]), row)
        if len(combined) == limit:
            break
    return list(combined.values())


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
    if re.search(r"归还|还书|超期", question) and re.search(r"寒假|暑假|暑期|假期|顺延|延期|超期|还书日", question):
        aspects.append("holiday_return")
    if re.search(r"复印", question):
        aspects.append("copy_return")
    if re.search(r"操作|如何|怎么|怎样|哪里|哪儿|平台|线上|办理|流程|入口", question):
        aspects.append("renewal_method")
    if not aspects or re.search(r"几次|多久|多长|多少|借期|本数|上限|借阅权限", question):
        aspects.append("renewal_rule")
    return aspects


def search_library(store, question, limit=5, today=None):
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
    loan_question = bool(_LOANS.search(_MACHINE.sub("", question)))
    realtime = bool(_REALTIME.search(question))
    reading_hours = bool(_HOURS.search(question)) and not realtime
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
    if date_error and (hours or "holiday_return" in _loan_aspects(question)):
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
        if kind == "regular" and day and re.search(r"延长|延时", question):
            scope["no_applicable_extension"] = True
        machine_supported = kind == "regular" and any(_MACHINE.search(row["text"]) for row in primary)
        if primary and (reading_hours or machine_supported):
            groups.append(_rank(store, question, primary, 1))
        if not primary and reading_hours:
            gaps.append("现有资料没有{}在所问日期适用的开放时间。".format(building))
        # 晚间延时只调整截止时间。兼问几点开馆时，才补充常规开馆资料。
        evening_only = primary and all(_scope(row).get("hours_aspect") == "evening_only" for row in primary)
        if evening_only and re.search(r"开馆|开门|几点(?:开|能进)", question):
            groups.append(_rank(store, question, regular, 1))
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
            temporary = [row for row, sc in applicable if sc["notice_kind"] == "temporary" and _active(sc, day)]
            policy = [row for row, sc in applicable if sc["notice_kind"] == "policy"
                      and sc.get("reader_group") in (None, scope["reader_group"])]
            # 生效的临时安排仅覆盖当前借阅事项，其他事项仍各自查找规则。
            selected = temporary or policy
            if selected:
                groups.append(_rank(store, question, selected, 1))
            else:
                gaps.append("现有资料没有适用于所问读者、馆舍或日期的借阅证据。")
        scope["campus"] = scope["campus"] or _CHENGDU

    hits = {}
    for group in groups:
        for row in group:
            hits.setdefault((row["version_id"], row["chunk_id"]), row)
    return list(hits.values())[:limit], scope
