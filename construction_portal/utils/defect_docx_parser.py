# -*- coding: utf-8 -*-
"""A 標缺失改善個別 docx 檔案解析器

輸入：一個 zip 含多份 docx 檔，或單一 docx bytes
輸出：list[dict]，每筆含 register_no + 抽取到的 缺失事項 / 改善中 / 改善後

支援兩種 layout：
- Legacy：Table 2 (3x2 或 3x1)，R0=缺失事項、R1=改善中、R2=改善後
- Standardized：Table 0 (3x3)，C1 欄分別為 缺失事項 / 改善中 / 改善後

兩種 layout 都有 `缺失事項：XXX` / `改善中：XXX` / `改善後：XXX` 這種 keyword
prefix，parser 就掃所有 tables 的所有 cell 文字，遇到就抽取。
"""

import re
import zipfile
from io import BytesIO


_LEGACY_RE = re.compile(r'^(\d{7})')
_STD_RE = re.compile(r'^(QA|QR)-(\d{7,8})')

_CATEGORY_TO_TYPE = {
    '品質': 'quality',
    '施工': 'quality',
    '職安': 'safety',
    '勞安': 'safety',
    '安衛': 'safety',
    '勞檢': 'safety',
    '環境': 'environmental',
}


def derive_defect_type(filename: str) -> str:
    """從檔名（含括號分類或 QA/QR 前綴）推導 defect_type。

    優先序：
    1. QA 前綴 → quality
    2. QR 前綴 → safety
    3. 檔名括號含 品質/施工/職安/勞安/安衛/勞檢/環境 → 對應
    4. 預設 'other'
    """
    bn = filename.rsplit('/', 1)[-1]
    if bn.upper().startswith('QA-'):
        return 'quality'
    if bn.upper().startswith('QR-'):
        return 'safety'
    for kw, val in _CATEGORY_TO_TYPE.items():
        if f'({kw})' in bn or f'（{kw}）' in bn or f'{kw}缺失' in bn:
            return val
    return 'other'


def derive_found_date(filename: str):
    """從檔名推導 found_date (ROC 年月日)。"""
    from datetime import date
    bn = filename.rsplit('/', 1)[-1]
    # standardized QA/QR-YYYMMDDNN
    m = _STD_RE.match(bn)
    if m:
        digits = m.group(2)[:7]
    else:
        m = _LEGACY_RE.match(bn)
        if not m:
            return None
        digits = m.group(1)
    try:
        year = int(digits[:3]) + 1911
        month = int(digits[3:5])
        day = int(digits[5:7])
        return date(year, month, day)
    except (ValueError, TypeError):
        return None

_FIELD_KEYS = {
    '缺失事項': 'description',
    '不符情形': 'description',
    '改善中': 'improvement',
    '改善後': 'close_comment',
}

# QA/QR layout 的照片 table：C1 column 放 改善前/改善中/改善後 label，
# 同列 (或前一列) C0 放 `照片內容：XXX`
_PHOTO_LABELS = {
    '改善中': 'improvement',
    '改善後': 'close_comment',
}


def derive_register_no(filename: str):
    """從檔名推導 Q01-YYYMMDD register_no，若無法推導回傳 None。"""
    bn = filename.rsplit('/', 1)[-1]
    m = _STD_RE.match(bn)
    if m:
        digits = m.group(2)
        return f'Q01-{digits[:7]}'
    m = _LEGACY_RE.match(bn)
    if m:
        return f'Q01-{m.group(1)}'
    return None


def _clean(text: str) -> str:
    return (text or '').strip().replace('\r\n', '\n').strip()


def _extract_from_prefix(text: str, prefix: str):
    """檢查 text 是否以 prefix: / prefix： 開頭，回傳冒號後的值或 None。"""
    for delim in ('：', ':'):
        key = prefix + delim
        if text.startswith(key):
            return _clean(text[len(key):])
    return None


def _split_after_colon(text: str) -> str:
    """抽 `prefix：value` / `prefix:value` 後面的 value；無冒號 → 原文。"""
    for delim in ('：', ':'):
        idx = text.find(delim)
        if idx >= 0:
            return _clean(text[idx + 1:])
    return _clean(text)


def _scan_photo_table(table) -> dict:
    """掃 QA/QR layout 的照片 table。

    照片 table 的 pattern：某列 C1 是 `改善中`/`改善後` label，
    其它 cell 的 `照片內容：XXX` 文字就是對應內容。
    同 label 下可能跨多列，取第一個非空值。
    """
    found = {}
    rows = list(table.rows)
    for i, row in enumerate(rows):
        label_field = None
        for cell in row.cells:
            txt = _clean(cell.text)
            if txt in _PHOTO_LABELS:
                label_field = _PHOTO_LABELS[txt]
                break
        if not label_field or label_field in found:
            continue

        # 在 label 當列 + 前一列 + 後一列中尋找 `照片內容：XXX`
        search_range = [i]
        if i > 0:
            search_range.insert(0, i - 1)
        if i + 1 < len(rows):
            search_range.append(i + 1)

        for j in search_range:
            seen = set()
            for cell in rows[j].cells:
                txt = _clean(cell.text)
                if not txt or txt in seen:
                    continue
                seen.add(txt)
                if txt.startswith('照片內容'):
                    val = _split_after_colon(txt)
                    if val and not val.startswith('照片內容'):
                        found[label_field] = val
                        break
            if label_field in found:
                break
    return found


def parse_defect_docx(docx_bytes: bytes) -> dict:
    """解析單一 docx，回傳 {description, improvement, close_comment}。

    支援三種 layout：
    1. Standardized 3x3 / Legacy Table2 3x1：cell text 內嵌 `缺失事項:/改善中:/改善後:` prefix
    2. Legacy Table1 多 row：`不符情形:XXX` 作為 description
    3. QA/QR 轉檔後的 Table1 照片 table：label + 照片內容 pattern
    """
    from docx import Document

    result = {'description': '', 'improvement': '', 'close_comment': ''}
    try:
        doc = Document(BytesIO(docx_bytes))
    except Exception:
        return result

    # Pass 1: keyword prefix scan (covers 缺失事項/不符情形/改善中/改善後 inline)
    for table in doc.tables:
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                text = _clean(cell.text)
                if not text or text in seen:
                    continue
                seen.add(text)
                for prefix, field in _FIELD_KEYS.items():
                    if result[field]:
                        continue
                    val = _extract_from_prefix(text, prefix)
                    if val:
                        result[field] = val
        if all(result.values()):
            return result

    # Pass 2: photo-label pattern (QA/QR Table1)
    for table in doc.tables:
        if not table.rows:
            continue
        header = _clean(table.rows[0].cells[0].text) if table.rows[0].cells else ''
        if '照片' not in header and '缺失改善' not in header:
            continue
        found = _scan_photo_table(table)
        for field, val in found.items():
            if not result[field]:
                result[field] = val

    return result


def parse_defect_zip(zip_bytes: bytes) -> list:
    """解析 zip 內所有 docx，回傳 list[dict]。

    每筆：
        {
            'filename': '1121025-磺港溪缺失矯正改善(勞安).docx',
            'register_no': 'Q01-1121025',  # 可能為 None
            'description': '...',
            'improvement': '...',
            'close_comment': '...',
            'error': str or None,
        }
    """
    results = []
    try:
        zf = zipfile.ZipFile(BytesIO(zip_bytes), 'r')
    except zipfile.BadZipFile:
        return results

    with zf:
        for name in zf.namelist():
            low = name.lower()
            if not low.endswith('.docx'):
                continue
            if name.startswith('__MACOSX') or '/__MACOSX' in name:
                continue

            reg = derive_register_no(name)
            entry = {
                'filename': name,
                'register_no': reg,
                'defect_type': derive_defect_type(name),
                'found_date': derive_found_date(name),
                'description': '',
                'improvement': '',
                'close_comment': '',
                'error': None,
            }
            try:
                parsed = parse_defect_docx(zf.read(name))
                entry.update(parsed)
            except Exception as e:
                entry['error'] = str(e)[:150]
            results.append(entry)

    return results
