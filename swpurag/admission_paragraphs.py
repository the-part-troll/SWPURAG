"""Keep applicant-specific paragraphs tied to the task and people they cover."""

import re


_FRESH = re.compile(
    r"(?<!非)(?<!不是)(?<!不属)应届|(?:本科|高校|大学).{0,12}(?:届时|预计|将于|明年)(?:20\d{2}年)?毕业"
)
_OTHER = re.compile(r"(?:非|不是|不属)应届|往届|已经毕业|已毕业|毕业.{0,8}(?:在上班|工作)")
_SITE = re.compile(r"报考点|考点|选点|选哪.{0,4}考试|去哪.{0,3}考试")
_MATERIAL = re.compile(r"材料|提交|上传|要传|证明|证件|户口簿|社保")
_SELF_STUDY = re.compile(r"自考|自学考试")
_COLLEGE_AGE = re.compile(r"(?:专科|大专).{0,20}(?:毕业|学历|文凭)|(?:专科|大专).{0,9}(?:年限|满|同等学力)")
_ADMISSION_REQUIREMENT = re.compile(r"年限|要满|满多久|几年|同等学力|报考资格|报考条件|能报考|能报吗")
_SPECIAL_REQUIREMENT = re.compile(r"单独考试|单考|专项|工商管理|公共管理|工程管理|旅游管理|教育管理|竞赛组织|125[1-6]\d{2}")
_PROVINCE = re.compile(r"四川|川内|全省|省内")
_PROVINCE_CAPACITY = re.compile(r"考位.{0,8}(?:够|紧张|充足|多少|容量)|(?:有|设|总共|整体).{0,10}考位")
_OVERALL_PROVINCE = re.compile(r"全省|省内.*整体|全四川")

# 只给具有明确对象/用途的问答段落加限制。标题与回答分别按原文识别，段落换位置仍可校验。
_FAQ_PARAGRAPHS = {
    "fresh_materials": re.compile(r"在我省报名参加考试的应届生需要提供哪些材料|(?<!非)应届生不需要提供户口证明"),
    "other_materials": re.compile(r"非应届毕业的其他考生在我省报名时需要提供哪些材料|户口在我省的应提供本人有效居民户口簿"),
    "fresh_site": re.compile(r"哪些应届生可以在四川省报名参加考试|在川高校应届毕业生.*外省高校应届毕业生"),
    "self_study_site": re.compile(r"四川省内参加自学考试届时可毕业的考生"),
    "province_capacity": re.compile(r"我省研招考试报考点考位容量是否充足|我省已设置近.*整体考位充足"),
}
_FULL_SITE_RULE = re.compile(r"应届本科毕业生.*教学点所在地.*其他考生.*工作或户籍所在地.*招生单位有特殊要求")
_JUNIOR_COLLEGE_RULE = re.compile(r"国家承认的高职\(专科\)毕业学历.*满2年.*毕业后到录取当年入学前.*同等学力身份报考")


def applicable_admission_paragraphs(rows, question, *, own_unit, exam_site):
    """Filter narrow FAQ paragraphs and identify evidence that covers a complete policy branch."""
    fresh = bool(_FRESH.search(question))
    older = bool(_OTHER.search(question))
    site = bool(_SITE.search(question)) or exam_site
    materials = bool(_MATERIAL.search(question))
    self_study = bool(_SELF_STUDY.search(question))
    ordinary_qualification = bool(_COLLEGE_AGE.search(question) and _ADMISSION_REQUIREMENT.search(question)
                                   and not _SPECIAL_REQUIREMENT.search(question))
    # 在川自考届时可毕业的考点材料，与已取得专科学历后的同等学力资格是不同用途。
    self_study_materials = self_study and site and materials and not ordinary_qualification
    allowed = {
        "fresh_materials": fresh and materials,
        "other_materials": materials and (older or not fresh or self_study),
        "fresh_site": fresh and site,
        "self_study_site": self_study and (site or materials),
        "province_capacity": bool(_PROVINCE.search(question) and _PROVINCE_CAPACITY.search(question)
                                  and (not exam_site or _OVERALL_PROVINCE.search(question))),
    }
    candidates = []
    priority = {"site_branches": [], "fresh_site": [], "self_study_site": [], "junior_college": []}
    for row in rows:
        role = row.get("role")
        body = re.sub(r"\s+", "", row["text"]).replace("（", "(").replace("）", ")")
        if role == "provincial_general":
            purpose = next((name for name, pattern in _FAQ_PARAGRAPHS.items() if pattern.search(body)), None)
            if purpose and not allowed[purpose]:
                continue
            if purpose == "fresh_site" and body.startswith(("答:", "答：")) and (older or _PROVINCE.search(question)):
                priority["fresh_site"].append(row)
            if purpose == "self_study_site" and body.startswith(("答:", "答：")):
                priority["self_study_site"].append(row)
        elif role == "exam_site" and fresh and older and site and _FULL_SITE_RULE.search(body):
            priority["site_branches"].append(row)
        elif role == "admission_unit" and _JUNIOR_COLLEGE_RULE.search(body):
            if self_study_materials:
                continue
            if ordinary_qualification and (own_unit or "章程" in question):
                priority["junior_college"].append(row)
        candidates.append(row)
    return candidates, priority
