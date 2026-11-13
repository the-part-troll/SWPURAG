"""Extract verifiable direction rows from a text-based admissions catalog."""

from io import BytesIO
import re
import unicodedata


_TITLE = re.compile(r"^.{4,100}?(非全日制|全日制)硕士研究生招生专业目录$")
_COLLEGE = re.compile(r"^\d{3}(?!\d)\S[^\n]*学院$")
_PROGRAM = re.compile(r"^([0-9]{4}[0-9A-Z][0-9])(?![0-9A-Za-z])\S[^\n]*$")
_DIRECTION = re.compile(r"^(\d{2})\((非全日制|全日制)\)\S[^\n]*$")
_NAME_COLUMN = ("name", "学院、专业、研究方向")
_DETAIL_COLUMNS = (("duration", "学制"), ("subjects", "考试科目"), ("remarks", "备注"))
# 用实际表头区分目录，避免混淆全日制含推免与非全日制不含单考的人数口径。
_LAYOUTS = {
    "非全日制": (_NAME_COLUMN, ("count", "拟招生非全日制人数(不含单考)")) + _DETAIL_COLUMNS,
    "全日制": (
        _NAME_COLUMN, ("recommended_count", "拟招推免人数"),
        ("count", "拟招全日制人数(含推免)"),
    ) + _DETAIL_COLUMNS + (("projects", "研究院实体化招生/企业联合培养项目"),),
}


def _compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _box(coords):
    return [round(value, 3) for value in coords]


def _source_cell(value, bbox, page, row):
    value = (value or "").strip()
    if value and bbox is not None:
        return {"text": value, "bbox": _box(bbox), "page": page, "row": row}
    return None


def _locator(page, table, row, bbox, cells, **fields):
    return dict(kind="pdf", page=page, table=table, row=row, bbox=_box(bbox),
                bbox_origin="top-left", bbox_unit="pt", cells=cells, **fields)


def _catalog_table(page):
    candidates = []
    for table_number, table in enumerate(sorted(page.find_tables(), key=lambda t: t.bbox), 1):
        values = table.extract()
        for index, row in enumerate(values):
            for mode, layout in _LAYOUTS.items():
                if len(row) == len(layout) and all(
                    _compact(value).startswith(label) for value, (_, label) in zip(row, layout)
                ):
                    candidates.append((table_number, table, values, index, mode))
    if len(candidates) != 1:
        raise ValueError("PDF 第 {} 页无法唯一确认专业目录表头".format(page.page_number))
    return candidates[0]


def _catalog_rows(page, table_number, table, values, header, mode):
    rows = table.rows
    left, _, right, bottom = table.bbox
    row_tops = [row.bbox[1] for row in rows] + [bottom]
    column_x = [cell[0] for cell in rows[header].cells]
    columns = {key: index for index, (key, _) in enumerate(_LAYOUTS[mode])}
    previous = [None] * len(columns)
    college = program = program_code = None
    program_counts = {}
    count_fields = [key for key in ("count", "recommended_count") if key in columns]
    labels = {key: "".join(values[header][column].splitlines()) for key, column in columns.items()}
    for index in range(header + 1, len(rows)):
        row_number = index + 1
        row_top, row_bottom = row_tops[index:index + 2]
        bbox = (left, row_top, right, row_bottom)
        boxes = rows[index].cells
        own = [_source_cell(value, box, page, row_number)
               for value, box in zip(values[index], boxes)]
        effective = list(own)
        for column, box in enumerate(boxes):
            if box is not None:
                previous[column] = own[column]
            elif previous[column] is not None:
                x, top, _, end = previous[column]["bbox"]
                # 只有合并格的坐标确实覆盖当前行才继承，空格和换页都会中断继承。
                if abs(x - column_x[column]) <= 0.01 and top < row_top and end + 0.01 >= row_bottom:
                    effective[column] = previous[column]

        first = own[0]
        if first is None or boxes[0][2] >= right - 0.01:
            continue  # 跨全表的说明行不改变当前专业归属。
        name = _compact(first["text"])
        if _COLLEGE.fullmatch(name):
            college = first
            program = program_code = None
            program_counts = {}
            continue
        major = _PROGRAM.fullmatch(name)
        if major:
            program = first
            program_code = major.group(1)
            program_counts = {key: own[columns[key]] for key in count_fields}
            continue

        direction = _DIRECTION.fullmatch(name)
        if not direction or direction.group(2) != mode:
            raise ValueError("PDF 第 {} 页第 {} 行目录层级无法确认".format(page, row_number))
        if not (college and program and effective[columns["subjects"]]):
            raise ValueError("PDF 第 {} 页第 {} 行缺少可定位的学院、专业或考试科目".format(page, row_number))
        details = [(key, labels[key], effective[columns[key]]) for key, _ in _DETAIL_COLUMNS]
        if any(cell and cell["row"] < program["row"] for _, _, cell in details):
            raise ValueError("PDF 第 {} 页第 {} 行的合并单元格跨专业".format(page, row_number))

        fields = [
            ("college", "学院", college),
            ("program", "专业", program),
            ("direction", "研究方向", first),
        ]
        # 专业与方向人数分别取自各自的行，方向格留空时不沿用专业合计。
        for key in count_fields:
            fields.append(("direction_" + key, "方向" + labels[key], own[columns[key]]))
            fields.append(("program_" + key, "专业" + labels[key], program_counts[key]))
        # 联合培养列可跨多个专业，不能据此认定某个方向参加该项目。
        fields.extend(details)
        yield {
            "text": "\n".join(label + "：" + cell["text"] for _, label, cell in fields if cell),
            "locator": _locator(
                page, table_number, row_number, bbox,
                {key: cell for key, _, cell in fields if cell},
                row_type="direction", program_code=program_code,
                direction_code=direction.group(1), study_mode=direction.group(2),
            ),
        }


def extract_pdf(body, sample):
    """Return title, positioned evidence chunks, and any explicit date fields."""
    try:
        import pdfplumber
        from pdfminer.psparser import PSException
        from pdfplumber.utils.exceptions import MalformedPDFException, PdfminerException
    except ImportError as error:
        raise ValueError("PDF 导入需要项目 SWPU_RAG 环境中的依赖，请按 environment.yml 配置") from error

    if not body.startswith(b"%PDF-"):
        raise ValueError("原件缺少 PDF 文件标记")
    title = None
    catalog_mode = None
    chunks = []
    try:
        with pdfplumber.open(BytesIO(body)) as pdf:
            for page in pdf.pages:
                table_number, table, values, header, mode = _catalog_table(page)
                page_number = page.page_number
                if page_number == 1:
                    title_lines = (values[0][0] or "").splitlines()
                    match = _TITLE.fullmatch(_compact(title_lines[0])) if title_lines else None
                    if header < 1 or not match:
                        raise ValueError("PDF 首页缺少可确认的招生专业目录标题")
                    title = title_lines[0]
                    catalog_mode = match.group(1)
                    expected_title = sample.get("title_hint") or sample.get("title")
                    if expected_title and _compact(expected_title) != _compact(title):
                        raise ValueError("PDF 标题与来源清单不符")
                    if len(title_lines) > 1:
                        box = table.rows[0].cells[0]
                        chunks.append({
                            "text": "\n".join(title_lines[1:]),
                            "locator": _locator(
                                page_number, table_number, 1, box,
                                {"note": _source_cell(values[0][0], box, page_number, 1)},
                                row_type="catalog_note",
                            ),
                        })
                if mode != catalog_mode:
                    raise ValueError("PDF 第 {} 页表头与目录标题的学习方式不符".format(page_number))
                page_chunks = list(_catalog_rows(page_number, table_number, table, values, header, mode))
                if not page_chunks:
                    raise ValueError("PDF 第 {} 页没有可核对的专业方向".format(page_number))
                chunks.extend(page_chunks)
                page.close()
    except (PSException, MalformedPDFException, PdfminerException) as error:
        raise ValueError("PDF 文件无法解析：{}".format(error)) from error
    if not title or not chunks:
        raise ValueError("PDF 没有可核对的招生专业方向")
    return title, chunks, {}
