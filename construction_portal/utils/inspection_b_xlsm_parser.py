# -*- coding: utf-8 -*-
"""B 標「自主檢查抽查彙整」xlsx 解析器

輸入：`▶自主檢查.抽查彙整-B-1130710V.xlsx` 之類的 B 標彙整檔
輸出：list[dict]，每筆可餵給 general.self.inspection.sudo().create()

結構：
- 多個 `總表 (YYYMMDD)` sheet，取最新一份（max_row 最多）
- R2 是類型 header（橫向），每欄 = 一種 inspection_type
- R3+ 是資料列，每格 `YYY/M/D|位置` 代表一次檢查事件
- 部分 cell 有 ● 或 ▲ 前綴，表示特殊標記（先忽略）
"""

import re
from datetime import date
from io import BytesIO


_DATE_SEP_RE = re.compile(r'(\d{2,3})[/.\-](\d{1,2})[/.\-](\d{1,2})')
_PREFIX_CHARS = '●▲○◎☆★△▼'


def _parse_roc_or_ad_date(text: str):
    """從 '112/9/23' 或 '2023/9/23' 擷取日期。"""
    if not text:
        return None
    m = _DATE_SEP_RE.search(text)
    if not m:
        return None
    try:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if y < 1911:
            y += 1911
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def _pick_sheet(wb):
    """挑資料最多的 sheet（max_row 最大）。"""
    best = None
    best_rows = 0
    for sn in wb.sheetnames:
        if '總表' not in sn and '抽查' not in sn:
            continue
        ws = wb[sn]
        if ws.max_row > best_rows:
            best_rows = ws.max_row
            best = sn
    if not best:
        best = wb.sheetnames[0]
    return best


def parse_inspection_b_xlsx(file_bytes: bytes, filename: str = '') -> list:
    """解析 B 標彙整檔回傳 list[dict]。

    每筆：
        {
            'type_name': '測量放樣-1',
            'inspection_date': date(2023, 9, 23),
            'location': '圍籬線放樣',
            'prefix': '',   # ● or ▲ or ''
        }
    """
    if not file_bytes:
        raise ValueError(f'檔案 {filename} 內容為空')

    try:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_filelike(BytesIO(file_bytes))
        sheets = wb.sheet_names
        # 挑「header 非空欄位最多」的 總表（最詳細版）
        best_sn = None
        best_cols = 0
        best_rows = None
        for sn in sheets:
            if '總表' not in sn and '抽查' not in sn:
                continue
            candidate_rows = list(wb.get_sheet_by_name(sn).to_python())
            # 找 header row
            hidx = 0
            for i, r in enumerate(candidate_rows[:5]):
                if r and r[0] and '項次' in str(r[0]):
                    hidx = i
                    break
            if hidx >= len(candidate_rows):
                continue
            hdr = candidate_rows[hidx]
            cols = sum(1 for v in hdr if v and str(v).strip() and str(v).strip() != '項次')
            if cols > best_cols:
                best_cols = cols
                best_sn = sn
                best_rows = candidate_rows
        if not best_rows:
            best_rows = list(wb.get_sheet_by_name(sheets[0]).to_python())
        rows = best_rows
    except Exception as e:
        raise ValueError(f'檔案 {filename} 無法開啟：{e}')

    if len(rows) < 2:
        return []

    # 動態找 header row：第一個 cell 值 == '項次' 的那列
    header_idx = 0
    for i, row in enumerate(rows[:5]):
        if row and row[0] and '項次' in str(row[0]):
            header_idx = i
            break

    header_row = rows[header_idx]
    type_map = {}
    for c_idx, val in enumerate(header_row):
        s = (str(val).strip() if val is not None else '')
        if s and s != '項次':
            type_map[c_idx] = s

    results = []
    for r_idx in range(header_idx + 1, len(rows)):
        row = rows[r_idx]
        for c_idx, type_name in type_map.items():
            if c_idx >= len(row):
                continue
            v = row[c_idx]
            if v is None or v == '':
                continue
            text = str(v).strip()
            # strip prefix chars
            prefix = ''
            if text and text[0] in _PREFIX_CHARS:
                prefix = text[0]
                text = text[1:].strip()

            d = _parse_roc_or_ad_date(text)
            if not d:
                continue
            # 取 | 或換行後的 location 部分
            parts = re.split(r'[|\n\r]+', text, maxsplit=1)
            location = parts[1].strip() if len(parts) > 1 else ''
            # 移除日期本身
            if not location:
                # 嘗試把日期 substring 從 text 抽掉剩下的當 location
                dm = _DATE_SEP_RE.search(text)
                if dm:
                    location = (text[:dm.start()] + text[dm.end():]).strip('|: -')
            # 與 A 標 parser 輸出兼容：補 sheet_label / note
            results.append({
                'sheet_label': f'B標|{type_name}',
                'type_seq': 0,
                'type_name': type_name,
                'seq_no': 0,
                'inspection_date': d,
                'location': location,
                'note': prefix or '',
            })

    return results
