# -*- coding: utf-8 -*-
"""缺失彙總表 xlsx 通用解析器

輸入：各案場的「缺失改善追蹤一覽表」xlsx
輸出：list[dict]，每筆可餵給 general/reservation.defect.improvement.sudo().create()

設計原則：**依表頭名稱讀欄，不依欄位位置**（與匯入.gs 的「A2 標題式」同一套原則）。
不預設工作表名、不預設表頭在第幾列、不預設欄位順序，因此同一支解析器能吃不同
案場的建檔慣例。

已知並實測支援的兩種格式
------------------------
A 標 `不合格品改善追蹤一覽表*.xlsx`
    工作表：不合格品改善追蹤一覽表 / 統計圖 / 工作表2
    表頭 R2、資料 R3 起
    編號 | 登錄編號 | 改正單位 | 改正事項 | 通知改正日期 | 限定完成改善日期 | 確認完成改善日期
    登錄編號形如 Q01-1121007；改正單位 職安/施工/環境；日期 112.10.07

P11001 `QA.QR-工程缺失改善追蹤一覽表.xlsx`
    工作表：QA / QR ← **工作表名即監造/營造**
    表頭 R4、資料 R5 起
    文件編號 | 工程缺失事項 | 通知改正日期 | 限定完成改善日期 | 確認完成改善日期 | 備註
    文件編號形如 QA-001；**無「改正單位」欄**；日期 110/08/03

處理方式
--------
1. 掃「所有」工作表。找不到可辨識表頭的工作表（統計圖、工作表2、封面…）自動略過，
   並記在回傳的 skipped 清單裡，不靜默丟棄。
2. 表頭偵測：往下掃前 12 列，某列若能對到「缺失說明 + 至少 2 個其它欄位」即視為表頭。
3. 欄位以別名表比對（正規化掉空白/換行/全形括號），長別名優先，避免「編號」搶走
   「登錄編號」。
4. `編號` 語意依內容判定：純數字 → 流水號；含英文/連字號 → 登錄編號。
   （A 標的 `編號` 是流水號、`登錄編號` 才是單號；P11001 的 `文件編號` 就是單號。）

此檔案含 embedded chart 會讓 openpyxl 丟 pitchFamily Max 52 錯誤，改用
python_calamine（Rust 底層 xlsx 解析器）。
"""

import re
from datetime import date, datetime
from io import BytesIO


# ── 日期 ────────────────────────────────────────────────────────────
# 民國 3 碼年：112.10.07 / 110/08/03 / 112-10-07
_ROC_DATE_RE = re.compile(r'^(\d{3})[.\-/](\d{1,2})[.\-/](\d{1,2})$')
# 西元 4 碼年：2023.10.07 / 2023/10/07
_AD_DATE_RE = re.compile(r'^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$')


def _parse_date(v):
    """把儲存格值轉成 datetime.date；無法判讀回 None。

    支援民國 3 碼年（112.10.07 / 110/08/03）、西元 4 碼年，以及 Excel
    真日期（calamine 會直接給 date/datetime）。
    """
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    m = _ROC_DATE_RE.match(s)
    if m:
        year = int(m.group(1)) + 1911
    else:
        m = _AD_DATE_RE.match(s)
        if not m:
            return None
        year = int(m.group(1))
    try:
        return date(year, int(m.group(2)), int(m.group(3)))
    except (ValueError, TypeError):
        return None


# 舊名保留，避免其它地方 import 時斷掉
_parse_roc_date = _parse_date


# ── 欄位別名（標題式定位） ──────────────────────────────────────────
# (邏輯欄位, 表頭別名)。比對時 alias 需為正規化後表頭的子字串。
# 長別名優先比對 —— 否則「編號」會搶走「登錄編號」「文件編號」。
_COLUMN_ALIASES = [
    ('register_no', '登錄編號'),
    ('register_no', '文件編號'),
    ('register_no', '缺失單號'),
    ('register_no', '紀錄表編號'),
    ('description', '工程缺失事項'),
    ('description', '缺失具體情形'),
    ('description', '改正事項'),
    ('description', '缺失事項'),
    ('description', '不符情形'),
    ('unit', '改正單位'),
    ('unit', '檢查類型'),
    ('found_date', '通知改正日期'),
    ('found_date', '通知改善日期'),
    ('found_date', '檢查日期'),
    ('found_date', '發現日期'),
    ('deadline', '限定完成改善日期'),
    ('deadline', '限期改善日期'),
    ('deadline', '改善期限'),
    ('improvement_date', '確認完成改善日期'),
    ('improvement_date', '實際改善日期'),
    ('improvement_date', '結案日期'),
    ('note', '備註'),
    # 語意曖昧，放最後：A標的「編號」是流水號，其它案場可能是單號。
    ('seq_or_register', '編號'),
]
_COLUMN_ALIASES.sort(key=lambda kv: -len(kv[1]))

# 表頭至少要對到這些才算數
_REQUIRED_KEY = 'description'
_MIN_MATCHED_KEYS = 3
_HEADER_SCAN_ROWS = 12

# 改正單位 → defect_category（general/reservation 詞彙）
UNIT_TO_CATEGORY = {
    '職安': 'safety',
    '勞安': 'safety',
    '安衛': 'safety',
    '勞檢': 'safety',
    '施工': 'workmanship',
    '品質': 'workmanship',
    '環境': 'environment',
}

# 沒有「改正單位」欄時，由工作表名 QA/QR 推論類別。
# 這是**代理推論**不是權威：QA/QR 嚴格說對應的是監造/營造（誰開的單），
# 與缺失類別是兩個維度，只是在這些案場高度重合。
_SHEET_TO_CATEGORY = {'QA': 'workmanship', 'QR': 'safety'}

# 純數字（用來判斷「編號」是流水號還是單號）
_PURE_INT_RE = re.compile(r'^\d+(\.0+)?$')


def _norm_header(v):
    """正規化表頭：去掉所有空白與換行，全形括號轉半形。"""
    if v is None:
        return ''
    s = str(v)
    s = re.sub(r'\s+', '', s)
    return s.replace('（', '(').replace('）', ')')


def _strip(v):
    if v is None:
        return ''
    return str(v).strip()


def _locate_header(rows):
    """在前幾列裡找表頭，回傳 (列索引, {邏輯欄位: 欄索引})；找不到回 (None, None)。"""
    for idx, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        if not row:
            continue
        colmap = {}
        for col, cell in enumerate(row):
            header = _norm_header(cell)
            if not header:
                continue
            for key, alias in _COLUMN_ALIASES:
                if key in colmap:
                    continue          # 這個邏輯欄位已被更前面的欄佔走
                if alias in header:
                    colmap[key] = col
                    break
        if _REQUIRED_KEY in colmap and len(colmap) >= _MIN_MATCHED_KEYS:
            return idx, colmap
    return None, None


def _cell(row, colmap, key):
    col = colmap.get(key)
    if col is None or col >= len(row):
        return None
    return row[col]


def parse_defect_tracking_xlsx(file_bytes: bytes, filename: str = '') -> list:
    """解析缺失彙總表，回傳 list[dict]。

    每筆：
        {
            'sheet_name': 'QA',                 # 供 record_type 第 2 層優先序
            'seq_no': 1,                        # 可能為 None
            'register_no': 'QA-001',            # 登錄編號，可能為 ''
            'unit': '職安',                     # 改正單位，可能為 ''
            'defect_category': 'safety',
            'category_inferred': False,         # True = 由工作表名推論，非來自資料
            'description': '安全帽未有反光帶。',
            'found_date': date(2023, 10, 7),
            'deadline': date(2023, 10, 12),
            'improvement_date': date(2023, 10, 7),   # or None
            'note': '',
        }

    另外掛一個屬性風格的 metadata 在回傳 list 上不方便，故略過的工作表以
    `parse_defect_tracking_xlsx.last_skipped` 形式無法多執行緒安全 ——
    改為在每筆結果帶 sheet_name，並由 `parse_defect_tracking_xlsx_verbose()`
    回傳 (rows, skipped)。本函式只回 rows，維持既有呼叫端相容。

    raise ValueError 當檔案無法開啟或完全找不到可辨識的缺失表。
    """
    rows, _skipped = parse_defect_tracking_xlsx_verbose(file_bytes, filename)
    return rows


def parse_defect_tracking_xlsx_verbose(file_bytes: bytes, filename: str = ''):
    """同 parse_defect_tracking_xlsx，但額外回傳被略過的工作表清單。

    :return: (list[dict], list[(sheet_name, 原因)])
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

    results = []
    skipped = []

    for sheet_name in wb.sheet_names:
        try:
            all_rows = list(wb.get_sheet_by_name(sheet_name).to_python())
        except Exception as e:
            skipped.append((sheet_name, f'讀取失敗：{e}'))
            continue

        header_idx, colmap = _locate_header(all_rows)
        if colmap is None:
            skipped.append((sheet_name, '找不到可辨識的缺失表頭'))
            continue

        # 沒有「改正單位」欄時，才用工作表名推論類別
        sheet_key = sheet_name.strip().upper()
        fallback_category = (_SHEET_TO_CATEGORY.get(sheet_key)
                             if 'unit' not in colmap else None)

        for row in all_rows[header_idx + 1:]:
            if not row:
                continue

            description = _strip(_cell(row, colmap, 'description')).replace('\n', ' ')
            found_date = _parse_date(_cell(row, colmap, 'found_date'))
            if not description or not found_date:
                continue   # 空列、統計列、小計列

            # 「編號」語意判定：純數字 → 流水號；其餘 → 登錄編號
            seq_no = None
            register_no = _strip(_cell(row, colmap, 'register_no'))
            raw_seq = _strip(_cell(row, colmap, 'seq_or_register'))
            if raw_seq:
                if _PURE_INT_RE.match(raw_seq):
                    seq_no = int(float(raw_seq))
                elif not register_no:
                    register_no = raw_seq

            unit = _strip(_cell(row, colmap, 'unit'))
            if unit:
                category = UNIT_TO_CATEGORY.get(unit, 'other')
                inferred = False
            else:
                category = fallback_category or 'other'
                inferred = bool(fallback_category)

            results.append({
                'sheet_name': sheet_name,
                'seq_no': seq_no,
                'register_no': register_no,
                'unit': unit,
                'defect_category': category,
                'category_inferred': inferred,
                'description': description,
                'found_date': found_date,
                'deadline': _parse_date(_cell(row, colmap, 'deadline')),
                'improvement_date': _parse_date(
                    _cell(row, colmap, 'improvement_date')),
                'note': _strip(_cell(row, colmap, 'note')),
            })

    if not results and not any(s for s in wb.sheet_names):
        raise ValueError(f'檔案 {filename} 沒有任何工作表')

    return results, skipped
