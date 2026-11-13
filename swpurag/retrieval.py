"""Lexical ranking for Chinese questions over current paragraph evidence."""

from collections import Counter, defaultdict
import math
import re

from .store import _search_text


_HAN = r"[\u3400-\u9fff\uf900-\ufaff]"
_HAN_CHAR = re.compile(_HAN)
_WORD = re.compile(_HAN + r"+|[a-z0-9]+")
_HAN_SPACE = re.compile(r"(?<=" + _HAN + r")\s+(?=" + _HAN + r")")
_CLAUSE_BREAK = re.compile(r"以及|还有|并且|[，。；！？、,;!?]")
_QUESTION_CLAUSE = re.compile(
    r"多久|多长时间|多少|几(?:个|年|月|天|日)|哪些|哪[里儿]|什么|"
    r"怎么|怎样|如何|何时|是否|能否|可否|能不能|要不要|是不是|吗$"
)
_DURATION_BOUND = re.compile(
    r"(?:要|须|需)?(至少|最少|超过|达到|满|间隔|相隔|累计|等待|持续|保持)"
    r"(?=多(?:久|长时间)|几(?:个)?[年月天日])"
)
_QUESTION_WORDS = re.compile(
    r"^(?:学校|本校|官网)(?:里|有|是)|"
    r"^我(?:已经|正在|想|准备|打算)?|请问|请帮我|帮我|我想知道|想了解|麻烦|能不能|可不可以|"
    r"是什么时候|什么时候|什么时间|是什么|在哪(?:里|儿|所|个)|哪(?:些|里|儿)|"
    r"哪(?:一|两|几)?(?:个|所|位|项|年|天)|多(?:少|久)|"
    r"怎么(?:样)?|如何|是否|何时|是哪个|分别|一下|的时候|(?<=\d)年|[的呢吗么]"
)
_CONTEXT_WORDS = {"学校", "本校", "官网", "老师", "请", "是", "在", "有", "和", "与", "及"}
_YEAR = re.compile(r"(?:19|20)[0-9]{2}")
_DATED_YEAR = re.compile(r"(?<![0-9])((?:19|20)[0-9]{2})\s*(?:年\s*\d{1,2}月|[-./]\d{1,2}(?![0-9]))")
_EDUCATION_ALIASES = {
    "大专": "专科",
    "研究生考试": "研考",
    "学费": "收费",
}


def _words(text):
    return _WORD.findall(_HAN_SPACE.sub("", _search_text(text)))


def _grams(word):
    # 中文取相邻两字，英文和专业代码保留整词。
    if word.isascii() or len(word) == 1:
        return [word]
    return [word[index:index + 2] for index in range(len(word) - 1)]


def _counts(words, single_han):
    counts = Counter(term for word in words for term in _grams(word))
    if single_han:
        counts.update(char for word in words if not word.isascii()
                      for char in word if char in single_han and len(word) > 1)
    return counts


def _query_clauses(query):
    clauses = []
    for clause in _CLAUSE_BREAK.split(_search_text(query)):
        # 去掉“多久”等问词时，保留“满”等会影响条件的词。
        clause = _DURATION_BOUND.sub(r" \1 ", clause)
        words = _WORD.findall(_QUESTION_WORDS.sub(" ", clause.strip()))
        words = [word for word in words if word not in _CONTEXT_WORDS]
        if words:
            terms = {word: set(_grams(word)) for word in words}
            for word in words:
                for colloquial, official in _EDUCATION_ALIASES.items():
                    if colloquial in word:
                        terms[official] = set(_grams(official))
            clauses.append(terms)
    return clauses


def _cohort_rows(rows, query, admission_year, explicit_years):
    # 招生届次限定候选文档，报考日期中的年份仍可参与排序。
    cohort_years = explicit_years - set(_DATED_YEAR.findall(_search_text(query)))
    for row in rows:
        year = row.get("admission_year")
        if admission_year is not None and str(year) != str(admission_year):
            continue
        if year is not None and cohort_years and str(year) not in cohort_years:
            continue
        yield row


def _supported_terms(clauses, doc_terms, years, shared_context):
    """Keep each clause's observed terms after checking explicit year scope."""
    supported = set()
    for clause in clauses:
        clause_years = {word for word in clause if _YEAR.fullmatch(word)}
        if clause_years and not clause_years.intersection(years):
            continue
        topic = {term for grams in clause.values() for term in grams} - shared_context
        supported.update(topic.intersection(doc_terms))
    return supported


def _snippet(text, terms, width=220):
    if len(text) <= width:
        return text
    # 规范化字符、去掉汉字间的空白时保留原始位置，摘录仍取自原文。
    normalized = []
    offsets = []
    for offset, char in enumerate(text):
        for unit in _search_text(char):
            normalized.append(unit)
            offsets.append(offset)
    normalized = "".join(normalized)
    removed = {index for match in _HAN_SPACE.finditer(normalized)
               for index in range(*match.span())}
    if removed:
        normalized = "".join(unit for index, unit in enumerate(normalized) if index not in removed)
        offsets = [offset for index, offset in enumerate(offsets) if index not in removed]
    for term in terms:
        pattern = re.escape(term)
        if term.isascii():
            pattern = r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])"
        match = re.search(pattern, normalized)
        if match is not None:
            start = max(0, min(offsets[match.start()] - width // 3, len(text) - width))
            end = max(start + width, offsets[match.end() - 1] + 1)
            return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
    return text[:width] + "…"


def search_natural(store, query, limit=5, admission_year=None, rows=None):
    """Rank body matches with BM25 and use titles to resolve document context."""
    if limit < 1:
        raise ValueError("Search limit must be positive")
    clauses = _query_clauses(query)
    query_terms = {term for clause in clauses for grams in clause.values() for term in grams}
    if not query_terms:
        return []
    # 改写后的词组可能只剩单字相同，单字仅辅助排序。入选仍需命中整词或相邻两字。
    single_han = {char for term in query_terms for char in term if _HAN_CHAR.fullmatch(char)}
    explicit_years = {term for term in query_terms if _YEAR.fullmatch(term)}
    query_words = {word for clause in clauses for word in clause}

    blocks = []
    document_terms = defaultdict(set)
    title_terms = {}
    unit_terms = []
    frequencies = Counter()
    pool = store.current_chunks() if rows is None else rows
    for row in _cohort_rows(pool, query, admission_year, explicit_years):
        body_words = _words(row["text"])
        counts = _counts(body_words, single_han)
        body_hits = query_terms.intersection(counts)
        document_id = row["document_id"]
        if document_id not in title_terms:
            title_terms[document_id] = query_terms.intersection(
                _counts(_words(row["title"]), single_han)
            )
            unit_terms.append({term for word in _words(row["unit"]) for term in _grams(word)})
        document_terms[document_id].update(body_hits | title_terms[document_id])
        frequencies.update((query_terms | single_han).intersection(counts))
        blocks.append((row, counts, body_hits))
    if not frequencies:
        return []

    # BM25 用候选段落的词频和平均长度定权，另给长数字代码加权。
    average_length = sum(sum(counts.values()) for _, counts, _ in blocks) / len(blocks)
    weights = {
        term: math.log1p((len(blocks) - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in frequencies.items()
    }
    for term in weights:
        if term not in query_terms:
            weights[term] *= 0.24
        elif term.isdigit() and len(term) >= 4 and term not in explicit_years:
            weights[term] *= 2.0
    # 排除候选文档共有的发布单位用语，避免仅凭校名等通用字词选出证据。
    shared_context = set.intersection(*unit_terms) if len(unit_terms) > 1 else set()
    matches = []
    supported = {}
    for row, counts, body_hits in blocks:
        document_id = row["document_id"]
        if document_id not in supported:
            doc_terms = document_terms[document_id]
            year = row.get("admission_year")
            years = doc_terms | {str(year)} if year is not None else doc_terms
            supported[document_id] = _supported_terms(clauses, doc_terms, years, shared_context)
        topic_hits = body_hits.intersection(supported[document_id])
        if not topic_hits:
            continue
        weak_hits = (single_han - query_terms).intersection(counts)
        norm = 1.2 * (0.25 + 0.75 * sum(counts.values()) / average_length)
        score = sum(weights[term] * (2.2 * counts[term]) / (counts[term] + norm)
                    for term in sorted(topic_hits | weak_hits))
        score += 0.30 * sum(weights.get(term, 0) for term in sorted(
            supported[document_id].intersection(title_terms[document_id])
        ))
        if _search_text(row["title"]).strip() in query_words:
            score *= 1.5
        result = dict(row, matched_terms=sorted(topic_hits, key=lambda term: (-weights[term], term)))
        matches.append((score, result))

    # 优先补充已选段落未覆盖的检索词，减少多个结果重复同一信息。
    results = []
    covered = set()
    while matches and len(results) < limit:
        def rank(candidate):
            score, row = candidate
            novel = set(row["matched_terms"]) - covered
            bonus = sum(weights[term] for term in sorted(novel))
            return -score - 0.55 * bonus, row["url"], row["ordinal"]

        best = min(range(len(matches)), key=lambda index: rank(matches[index]))
        _, result = matches.pop(best)
        covered.update(result["matched_terms"])
        result["snippet"] = _snippet(result["text"], result["matched_terms"])
        results.append(result)
    return results


def rank_candidates(store, query, limit, admission_year=None, rows=None, *,
                    ranker=None, trace=None, topic="admissions", stage="global", fallback=False):
    """Rank the complete applicable pool, with the existing lexical ordering as a callback."""
    if limit < 1:
        raise ValueError("Search limit must be positive")
    pool = store.current_chunks() if rows is None else rows
    years = {word for clause in _query_clauses(query) for word in clause if _YEAR.fullmatch(word)}
    candidates = list(_cohort_rows(pool, query, admission_year, years))

    def lexical(count):
        ranked = search_natural(store, query, count, admission_year, candidates)
        if not fallback:
            return ranked
        # 图书馆先锁定可用条款。问句改写没有词法匹配时仍保留该条款。
        result = {}
        for row in ranked + candidates:
            result.setdefault((row["version_id"], row["chunk_id"]), row)
            if len(result) == count:
                break
        return list(result.values())

    if ranker is None:
        hits = lexical(limit)
    else:
        allowed = {(row["version_id"], row["chunk_id"]): row for row in candidates}
        ranked = ranker(query, candidates, limit, lexical) if candidates else ()
        hits_by_key = {}
        for hit in ranked:
            key = hit["version_id"], hit["chunk_id"]
            if key not in allowed:
                raise ValueError("Ranker selected evidence outside the candidate scope")
            # 排名器可提供分数和摘要，引用的正文和位置以原始候选为准。
            hits_by_key.setdefault(key, dict(hit, **allowed[key]))
            if len(hits_by_key) == limit:
                break
        hits = list(hits_by_key.values())
    if trace is not None:
        trace.append({
            "topic": topic, "stage": stage, "query": query,
            "candidate_ids": [row["chunk_id"] for row in candidates],
            "ranked_ids": [row["chunk_id"] for row in hits],
        })
    return hits


def explicit_subquestions(query):
    """Conservatively select separate clauses with their own question marker."""
    clauses = (clause.strip() for clause in _CLAUSE_BREAK.split(query))
    questions = list(dict.fromkeys(clause for clause in clauses if _QUESTION_CLAUSE.search(clause)))
    return questions if 2 <= len(questions) <= 5 else []


def search_admission_question(store, query, limit, admission_year, rows=None, reserved=(), *,
                              ranker=None, trace=None):
    """Reserve one evidence slot per explicit subquestion, then fill globally."""
    global_hits = rank_candidates(store, query, limit, admission_year, rows, ranker=ranker, trace=trace)
    questions = explicit_subquestions(query)
    if not questions and not reserved:
        return global_hits
    if not global_hits and not reserved:
        if trace is not None:
            for question in questions:
                rank_candidates(store, question, 1, admission_year, rows, ranker=ranker,
                                trace=trace, stage="subquestion")
        return []
    # 范围检索预留的证据优先，随后为各个明确子问取首条，再用全问结果补足。
    candidates = [
        hit for question in questions
        for hit in rank_candidates(store, question, 1, admission_year, rows, ranker=ranker,
                                   trace=trace, stage="subquestion")
    ]
    results = {}
    for hit in list(reserved) + candidates + global_hits:
        key = hit["version_id"], hit["chunk_id"]
        results.setdefault(key, hit)
        if len(results) == limit:
            break
    return list(results.values())
