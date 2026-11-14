"""Select admissions directory evidence by study mode, college and program."""

import re

from .retrieval import (
    exam_site_refund_scenarios, explicit_subquestions, mentions_exam_site, rank_candidates,
    search_admission_question,
)
from .store import _search_text


MODES = ("全日制", "非全日制")
_MODE = re.compile(r"非全日制|全日制")
_TARGET_MODE = re.compile(r"(?:报考|报|读|申请|选择)(?:的是)?(?:20\d{2}年)?(非全日制|全日制)")
_COMPARE = re.compile(r"对比|比较|区别|差异|分别|一样|相同|各自|两份目录|两种学习方式|两边")
_BOTH_MODES = re.compile(r"两份目录|两种学习方式|全日制(?:和|与|及|、)非全日制|非全日制(?:和|与|及|、)全日制")
_CODE = re.compile(r"(?<![a-z0-9])\d{4}[a-z0-9]{2}(?![a-z0-9])")
_POLICY = re.compile(r"章程|报考条件|报考资格|工作经验|学费|收费标准|同等学力报考")
_SPECIAL_EXAM = re.compile(r"(?:报考|报|参加|走)(?:我校|学校|该校)?(?:单独考试|单考|退役大学生士兵专项)")
_AFFIRMATIVE = r"(?<!不)(?<!没)(?<!不是)"
_APPLY = r"(?:报考|报名|(?<!报)考|报|申请)(?:的是|是|的|了)?"
_OTHER_SCHOOL = r"外校|(?:其他|别的|另一所|别所)(?:高校|学校|大学|院校)"
_OTHER_UNIT = re.compile(
    rf"{_AFFIRMATIVE}(?:{_APPLY}|招生单位(?:是|为|选的是))(?:{_OTHER_SCHOOL})"
)
_OWN_UNIT = re.compile(
    rf"{_AFFIRMATIVE}(?:{_APPLY}|招生单位(?:是|为|选的是))"
    r"(?:西南石油大学|西油|本校|该校|10615(?!\d))(?!的?(?:校?本部|考点|报考点|5110))"
)
_REFUND_EVIDENCE = {
    "cancel": re.compile(r"取消[^。]{0,18}报名[^。]{0,60}退费"),
    "absent": re.compile(r"确认[^。]{0,14}未参加考试[^。]{0,24}(?:不予退还|不退费)"),
}
_DETAIL_FIELDS = {
    "subjects": re.compile(r"科目|初试|第[一二三四1234]门|考什么|考哪|专业课"),
    "direction": re.compile(r"方向|研究方向"),
    "program_count": re.compile(r"人数|人吗|多少人|几人|名额|招生计划|拟招"),
    "duration": re.compile(r"学制|读几年"),
    "remarks": re.compile(r"复试|加试"),
}
_COLLEGE_ALIASES = {
    "石油与天然气工程学院": ("石工院", "石工学院", "石油工程学院"),
    "经济管理学院": ("经管学院", "经管院"),
    "计算机与软件学院": ("计软学院", "计软院", "计算机学院"),
    "土木工程与测绘学院": ("土测学院", "土测院"),
}


def _compact(text):
    return re.sub(r"\s+", "", _search_text(text))


def _cell(row, key):
    return row["locator"].get("cells", {}).get(key, {}).get("text", "")


def _college(row):
    return re.sub(r"^\d{3}", "", _compact(_cell(row, "college")))


def _mode(row):
    recorded = row["locator"].get("study_mode")
    if recorded:
        return recorded
    match = _MODE.search(row["title"])
    return match.group() if match else None


def _program(row):
    name = re.sub(r"^[a-z0-9]{6}", "", _compact(_cell(row, "program")))
    return re.sub(r"\([^)]*\)", "", name).strip()


def _direction(row):
    return re.sub(r"^\d{2}\((?:非)?全日制\)", "", _compact(_cell(row, "direction")))


def directory_scope(row):
    if row.get("role") == "admission_directory" and row["locator"].get("row_type") == "direction":
        return _mode(row), _college(row)
    return None


def _has_difference(rows, group_by, fields):
    groups = {}
    for row in rows:
        values = tuple(_direction(row) if field == "direction" else _compact(_cell(row, field))
                       for field in fields)
        groups.setdefault(group_by(row), set()).add(values)
    return len({frozenset(values) for values in groups.values()}) > 1


def _mentioned_colleges(query, names):
    return {name for name in names if any(alias in query for alias in (name,) + _COLLEGE_ALIASES.get(name, ()))}


def _pair_comparison(query, targets, colleges):
    if len(colleges) < 2:
        return targets
    # 仅在分句明确给出两种学习方式各自的学院时保留配对，避免交叉组合。
    starters = [mode for mode in MODES]
    for college in colleges:
        starters.extend((college,) + _COLLEGE_ALIASES.get(college, ()))
    split = r"[,，。;；!?！？]|(?:和|与|及)(?=(?:" + "|".join(map(re.escape, starters)) + "))"
    paired = {}
    for segment in re.split(split, query):
        modes = set(_MODE.findall(segment))
        local = _mentioned_colleges(segment, colleges)
        if len(modes) == 1 and local:
            mode = modes.pop()
            paired.setdefault(mode, set()).update(local)
    if set(paired) == set(MODES):
        return [row for row in targets if _college(row) in paired.get(_mode(row), ())]
    return targets


def _refund_rows(rows):
    groups = {scenario: [] for scenario in _REFUND_EVIDENCE}
    for row in rows:
        if row.get("role") == "exam_site":
            for scenario, pattern in _REFUND_EVIDENCE.items():
                if pattern.search(_compact(row["text"])):
                    groups[scenario].append(row)
    return groups


def search_scoped(store, question, limit, admission_year, *, ranker=None, trace=None):
    """Return ranked evidence and any missing scope that changes the answer."""
    query = _compact(question)
    rows = [row for row in store.current_chunks() if row.get("admission_year") == admission_year]
    external_site = mentions_exam_site(query) and _OTHER_UNIT.search(query) and not _OWN_UNIT.search(query)
    if external_site:
        # 此处的招生单位公告、章程和目录均面向报考西南石油大学的考生。
        rows = [row for row in rows if row.get("role") not in {"admission_unit", "admission_directory"}]
    directories = [row for row in rows if row.get("role") == "admission_directory"]
    directions = [row for row in directories if row["locator"].get("row_type") == "direction"]
    modes = tuple(dict.fromkeys(_MODE.findall(query)))
    comparison = bool(_COMPARE.search(query) or _BOTH_MODES.search(query))
    compare_modes = comparison and (len(modes) == 2 or bool(_BOTH_MODES.search(query)))
    if compare_modes:
        modes = MODES
    elif len(modes) == 2:
        # 同时提到两种方式不一定是比较，优先取“报考”等动作明确指向的一种。
        target = _TARGET_MODE.search(query)
        modes = (target.group(1),) if target else ()
    colleges = sorted(_mentioned_colleges(query, {_college(row) for row in directions if _college(row)}))
    codes = sorted(set(_CODE.findall(query)))
    fields = [field for field, pattern in _DETAIL_FIELDS.items() if pattern.search(query)]
    catalog_lookup = bool(fields or modes or colleges or comparison)
    special_exam = bool(_SPECIAL_EXAM.search(query))
    identified = [row for row in directions if
                  (row["locator"].get("program_code", "").lower() in codes if codes
                   else len(_program(row)) >= 2 and _program(row) in query)]
    named = [row for row in identified if len(_direction(row)) >= 2 and _direction(row) in query]
    targets = named or identified
    targets = [row for row in targets if (not modes or _mode(row) in modes)
               and (not colleges or _college(row) in colleges)]
    if compare_modes:
        targets = _pair_comparison(query, targets, colleges)
    if "program_count" in fields and "direction" in fields:
        fields.append("direction_count")

    # 缺失的范围确实会改变所问字段时才澄清。先比较学习方式，再比较同一方式下的学院和方向。
    clarify = []
    if fields and targets and not special_exam:
        if not modes and _has_difference(targets, _mode, fields):
            clarify.append("学习方式（全日制或非全日制）")
        if not colleges and any(
            _has_difference([row for row in targets if _mode(row) == mode], _college, fields)
            for mode in {_mode(row) for row in targets}
        ):
            clarify.append("报考学院")
        if not named and not comparison and re.search(r"第四门|专业课", query) and any(
            _has_difference([row for row in targets if (_mode(row), _college(row)) == group],
                            _direction, ("subjects",))
            for group in {(_mode(row), _college(row)) for row in targets}
        ):
            clarify.append("研究方向")
    eligible_ids = {row["chunk_id"] for row in targets}
    pool = []
    for row in rows:
        if row.get("role") == "admission_directory":
            # 普通目录不适用于单独考试等特殊类别，章程等材料仍可用于核对规则。
            if special_exam:
                continue
            if row["locator"].get("row_type") == "direction":
                if (modes and _mode(row) not in modes) or (colleges and _college(row) not in colleges):
                    continue
                if catalog_lookup and (codes or identified) and row["chunk_id"] not in eligible_ids:
                    continue
            elif modes and _mode(row) not in modes:
                continue
        pool.append(row)

    # 对比时为每侧预留证据。兼问政策时另留政策段落，避免都被目录条目占用。
    reserved = []
    refunds = exam_site_refund_scenarios(question)
    if refunds:
        groups = _refund_rows(pool)
        excluded = {row["chunk_id"] for kind, matches in groups.items() if kind not in refunds for row in matches}
        pool = [row for row in pool if row["chunk_id"] not in excluded]
        # 两种退费情形各自取证。即使问句用“撤单”或“没去考”，也保留可核对的正式条款。
        for kind in refunds:
            reserved.extend(rank_candidates(store, question, 1, admission_year, groups[kind],
                                            ranker=ranker, trace=trace, stage="refund:" + kind,
                                            fallback=True))
    if targets and catalog_lookup and not special_exam:
        if compare_modes:
            for mode in modes:
                subset = [row for row in targets if _mode(row) == mode]
                reserved.extend(rank_candidates(store, question, 1, admission_year, subset,
                                                ranker=ranker, trace=trace, stage="reserved_mode"))
        elif comparison and len(colleges) > 1:
            for college in colleges:
                subset = [row for row in targets if _college(row) == college]
                reserved.extend(rank_candidates(store, question, 1, admission_year, subset,
                                                ranker=ranker, trace=trace, stage="reserved_college"))
        elif fields:
            reserved.extend(rank_candidates(store, question, 1, admission_year, targets,
                                            ranker=ranker, trace=trace, stage="reserved_directory"))

        if _POLICY.search(query):
            policy_rows = [row for row in pool if row.get("role") != "admission_directory"]
            policy_query = next((part for part in explicit_subquestions(question) if _POLICY.search(part)), question)
            reserved.extend(rank_candidates(store, policy_query, 1, admission_year, policy_rows,
                                            ranker=ranker, trace=trace, stage="reserved_policy"))

    hits = search_admission_question(store, question, limit, admission_year, pool, reserved,
                                     ranker=ranker, trace=trace)
    scope = {"study_modes": list(modes), "colleges": colleges, "program_codes": codes,
             "compare_modes": compare_modes, "special_exam": special_exam}
    if clarify:
        scope["clarification"] = "请补充您的" + "、".join(clarify) + "，以便核对对应的目录记录。"
    return hits, scope
