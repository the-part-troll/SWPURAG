"""Filter school calendar paragraphs by the dates and arrangements they cover."""

from datetime import date, datetime, timedelta, timezone
import re

from .retrieval import rank_candidates
from .store import _search_text


_HOLIDAYS = {
    "中秋": "中秋节", "国庆": "国庆节", "元旦": "元旦", "春节": "春节", "清明": "清明节",
    "五一": "劳动节", "劳动节": "劳动节", "端午": "端午节", "寒假": "寒假", "暑假": "暑假",
}
_HOLIDAY = re.compile("|".join(_HOLIDAYS))
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*年")
_FULL_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:\s*年\s*|[-/.])(\d{1,2})(?:\s*月\s*|[-/.])(\d{1,2})\s*[日号]?(?!\d)")
_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?(?!\d)")
_RELATIVE = {"前天": -2, "昨天": -1, "今天": 0, "今日": 0, "明天": 1, "后天": 2}
_CLASS = re.compile(r"调休|上课|上班|有(?:没有)?课|没课|补课|补班|课表|课程")
_HOLIDAY_DATES = re.compile(r"放.{0,8}假|放(?:哪[几一]?|几)天|假期|休假|休几天|休哪几天|哪天开始休|休到几号|从哪天放到哪天")
_MAKEUP_DATES = re.compile(r"补课|补班|调休.{0,12}(?:哪些|哪天|几号|哪几天|哪两个|周末|上课|上班)")
_SCHEDULE = re.compile(r"课表|课程|补.{0,8}(?:的课|星期几|周几)|(?:具体|哪[一门些])[^？?。]{0,8}上什么课")
_COLLEGE = re.compile(r"学院|院系|专业|班级|年级|校区")


def _query_dates(text, today):
    full = [date(*map(int, match.groups())) for match in _FULL_DATE.finditer(text)]
    years = {day.year for day in full} | {int(year) for year in _YEAR.findall(text)}
    default_year = next(iter(years)) if len(years) == 1 else today.year
    other = _FULL_DATE.sub(" ", text)
    partial = [date(default_year, *map(int, match.groups())) for match in _MONTH_DAY.finditer(other)]
    relative = [today + timedelta(days=offset) for name, offset in _RELATIVE.items() if name in text]
    dates = sorted({day.isoformat() for day in full + partial + relative})
    source = "explicit" if full or (partial and years) else "assumed_year" if partial else "relative" if relative else None
    return dates, years | {int(day[:4]) for day in dates} or {today.year}, source


def search_calendar(store, question, limit, *, ranker=None, trace=None, today=None):
    query = _search_text(question)
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    holidays = list(dict.fromkeys(_HOLIDAYS[name] for name in _HOLIDAY.findall(query)))
    scope = {"topic": "school_calendar", "holidays": holidays, "unsupported": []}
    try:
        dates, years, source = _query_dates(query, today)
    except ValueError:
        scope["clarification"] = "请提供有效的公历日期。"
        return [], scope
    if len(years) != 1:
        scope["clarification"] = "请逐年查询，或说明各个假期分别对应哪一年。"
        return [], scope
    scope.update(year=next(iter(years)), date=dates[0] if len(dates) == 1 else None, date_source=source)
    gaps = scope["unsupported"]
    if _SCHEDULE.search(query):
        gaps.append("现有校级通知未说明补哪天的课或具体课表，请查阅教务通知或所在学院的安排。")
    if _COLLEGE.search(query):
        gaps.append("现有资料无法确认所问学院、校区或班级是否另有安排，请查阅对应单位通知。")

    class_question = bool(_CLASS.search(query))
    holiday_question = bool(_HOLIDAY_DATES.search(query))
    makeup_only = class_question and not holiday_question and bool(_MAKEUP_DATES.search(query))
    candidates = []
    covered_days = set()
    covered_holidays = set()
    for row in store.current_chunks(topic="school_calendar"):
        period = row["locator"]["calendar_scope"]
        name = period["holiday"]
        if period["year"] not in years or holidays and name not in holidays:
            continue
        makeup = period["makeup_dates"]
        if dates:
            days = [day for day in dates if day in makeup
                    or (not makeup_only and period["effective_from"] <= day <= period["effective_to"])]
            # 问某日是不是指定假期时，也可以用已知起止判断该日是否在范围外。
            if holidays and holiday_question and not makeup_only:
                days = dates
            if not days:
                continue
            covered_days.update(days)
        elif ((makeup_only or class_question and not holiday_question) and not makeup
              or not holidays and not _MAKEUP_DATES.search(query)):
            continue
        covered_holidays.add(name)
        candidates.append(row)

    if not candidates or set(dates) - covered_days or set(holidays) - covered_holidays:
        gaps.append("现有校级通知未覆盖所问的假期、年份或日期，无法确认相应的放假或上课安排。")
    ranked = rank_candidates(store, question, limit, rows=candidates, ranker=ranker, trace=trace,
                             topic="school_calendar", stage="calendar_dates", fallback=True)
    return ranked, scope
