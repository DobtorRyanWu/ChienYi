# -*- coding: utf-8 -*-
"""A 標「不合格品改善追蹤一覽表」xlsx 解析器

輸入：`不合格品改善追蹤一覽表115.02.26.xlsx` 之類的缺失彙總檔
輸出：list[dict]，每筆可餵給 supervision.defect.sudo().create()

此檔案含 embedded chart 會讓 openpyxl 丟 pitchFamily Max 52 錯誤，
改用 python_calamine（Rust 底層 xlsx 解析器）。

Sheet `不合格品改善追蹤一覽表` 結構：
    R1  (標題) 磺港溪再造C段... 不合格品改善追蹤一覽表
    R2  (header) 編號 | 登錄編號 | 改正單位 | 改正事項 | 通知/改正日期 | 限定完成改善日期 | 確認完成改善日期
    R3+ data rows

C8/C9 是 統計圖 用的 embedded stats data (施工/職安/環境 counts)，忽略。

改正單位 (C3) → defect_type:
    職安 → safety
    施工 → quality
    環境 → environmental
    其它 → other
"""

import re
from datetime import date
from io import BytesIO


_ROC_DATE_RE = re.compile(r'^(\d{3})[.\-/](\d{1,2})[.\-/](\d{1,2})$')

UNIT_TO_DEFECT_TYPE = {
    '職安': 'safety',
    '施工': 'quality',
    '環境': 'environmental',
    '品質': 'quality',
    '勞安': 'safety',
}


def _parse_roc_date(v):
    """將 '112.10.07' / '113.3.11' 之類民國年轉成 datetime.date。"""
    if v is None or v == '':
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    m = _ROC_DATE_RE.match(s)
    if not m:
        return None
    try:
        year = int(m.group(1)) + 1911
        month = int(m.group(2))
        day = int(m.group(3))
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _strip(v):
    if v is None:
        return ''
    return str(v).strip()


def parse_defect_tracking_xlsx(file_bytes: bytes, filename: str = '') -> list:
    """解析不合格品改善追蹤一覽表，回傳 list[dict]。

    每筆：
        {
            'seq_no': 1,
            'register_no': 'Q01-1121007',
            'unit': '職安',
            'defect_type': 'safety',
            'description': '安全帽未有反光帶。',
            'found_date': date(2023, 10, 7),
            'deadline': date(2023, 10, 12),
            'improvement_date': date(2023, 10, 7),  # or None
        }

    raise ValueError 當檔案無法開啟或缺少指定 sheet。
    """
    if not file_bytes:
        raise ValueError(f'檔案 {filename} 內容為空')

    try:
        from python_calamine import CalamineWorkbook
    except ImportError as e:
        raise ValueError(f'缺少 python_calamine 套件：{e}')

    try:
        wb = CalamineWorkbook.from_filelike(BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f'檔案 {filename} 無法開啟：{e}')

    target_sheet = None
    for name in wb.sheet_names:
        if '不合格品' in name or '缺失' in name:
            target_sheet = name
            break
    if not target_sheet:
        target_sheet = wb.sheet_names[0]

    ws = wb.get_sheet_by_name(target_sheet)
    all_rows = list(ws.to_python())

    results = []
    # Data rows 從 R3 起（R1=標題、R2=header）
    for row in all_rows[2:]:
        if not row:
            continue
        if len(row) < 5:
            continue
        seq_raw = row[0] if len(row) > 0 else None
        if seq_raw in (None, ''):
            continue
        try:
            seq_no = int(float(seq_raw))
        except (TypeError, ValueError):
            continue

        register_no = _strip(row[1]) if len(row) > 1 else ''
        unit = _strip(row[2]) if len(row) > 2 else ''
        description = _strip(row[3]).replace('\n', ' ') if len(row) > 3 else ''
        found_date = _parse_roc_date(row[4]) if len(row) > 4 else None
        deadline = _parse_roc_date(row[5]) if len(row) > 5 else None
        improvement_date = _parse_roc_date(row[6]) if len(row) > 6 else None

        if not description or not found_date:
            continue

        defect_type = UNIT_TO_DEFECT_TYPE.get(unit, 'other')

        results.append({
            'seq_no': seq_no,
            'register_no': register_no,
            'unit': unit,
            'defect_type': defect_type,
            'description': description,
            'found_date': found_date,
            'deadline': deadline,
            'improvement_date': improvement_date,
        })

    return results