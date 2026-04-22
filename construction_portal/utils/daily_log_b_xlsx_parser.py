# -*- coding: utf-8 -*-
"""B 標「三合橋施工日誌」xlsx 解析器

輸入：`三合橋施工日誌1131006.xlsx` 之類的 B 標每日施工日誌（每檔 1 天）
輸出：dict 可餵給 daily.log.sheet.create()

結構（sheet '日報'，66 rows）：
    R00: 公共工程施工日誌
    R01: 表報編號：N
    R02: 本日天氣：上午：晴   下午：雨 | (C6) 填表日期 | (C9) Excel serial date
    R03: 工程名稱 | 承攬廠商名稱
    R04: 核定工期 / 累計工期 / 剩餘工期 / 工期展延
    R05: 開工日期 / 完工日期
    R06: 預定進度(%) | (C10) 實際進度(%)
    R07: 一、(header)
    R08: header: 施工項目 | (C5) 單位 | (C6) 契約數量 | (C8) 本日完成 | (C10) 累計完成 | (C12) 備註
    R09+: data rows until R17 '營造業專業工程特定施工項目'
    R20: 二、(header)
    R21: header: 材料名稱 | (C4) 單位 | (C5) 契約數量 | (C7) 本日使用 | (C9) 累計使用 | (C11) 備註
    R22+: data rows
    R28: 三、(skip)
    R35: 四、技術士
    R37: 五、安衛
    R44: 六、試驗紀錄
    R48: 七、協力廠商
    R50+: 八、重要事項
"""

import re
from datetime import date, datetime, timedelta
from io import BytesIO


WEATHER_MAP = {
    '晴': 'sunny', '晴天': 'sunny', '晴時多雲': 'sunny',
    '多雲': 'cloudy', '多雲時晴': 'cloudy',
    '陰': 'overcast', '陰天': 'overcast', '多雲時陰': 'overcast',
    '雨': 'rainy', '雨天': 'rainy', '小雨': 'rainy', '下雨': 'rainy', '陣雨': 'rainy',
    '豪雨': 'heavy_rain', '大雨': 'heavy_rain', '暴雨': 'heavy_rain',
    '颱風': 'typhoon',
    '霧': 'foggy', '有霧': 'foggy',
}

SECTION_MARKERS = ('一、', '二、', '三、', '四、', '五、', '六、', '七、', '八、')


def _map_weather(s):
    s = (s or '').strip()
    if not s:
        return False
    return WEATHER_MAP.get(s, False)


def _parse_weather_cell(text):
    """parse '本日天氣：上午：晴   下午：雨' → ('sunny', 'rainy')"""
    if not text:
        return False, False
    am_match = re.search(r'上午[:：]\s*(\S+?)(?:\s|下午|$)', text)
    pm_match = re.search(r'下午[:：]\s*(\S+)', text)
    am = _map_weather(am_match.group(1)) if am_match else False
    pm = _map_weather(pm_match.group(1)) if pm_match else False
    return am, pm


def _excel_serial_to_date(v):
    """Excel serial number → python date. Epoch 1900-01-01 (with 1900 leap bug)."""
    if v is None or v == '':
        return None
    if isinstance(v, date):
        return v if not isinstance(v, datetime) else v.date()
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n < 1 or n > 100000:
        return None
    # Excel epoch: day 1 = 1900-01-01, but 1900 is wrongly considered leap so -2 offset
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=n)).date()


def _parse_roc_from_filename(fname):
    """檔名若含 ROC 日期段（如 1131125-1131201），取最後那個作為 log_date。"""
    if not fname:
        return None
    matches = re.findall(r'\d{7}', fname)
    if not matches:
        return None
    raw = matches[-1]  # 取最後一個（通常是範圍結尾或檔名結尾）
    try:
        y = int(raw[:3]) + 1911
        mo = int(raw[3:5])
        d = int(raw[5:7])
        return date(y, mo, d)
    except (ValueError, IndexError):
        return None


def _strip(v):
    if v is None:
        return ''
    return str(v).strip()


def _num(v):
    if v is None or v == '':
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _find_row(rows, start, end, prefix):
    for r in range(start, min(end, len(rows))):
        first = rows[r][0] if rows[r] else None
        if first and str(first).strip().startswith(prefix):
            return r
    return None


def _collect_text(rows, start, end):
    parts = []
    for r in range(start, min(end, len(rows))):
        row = rows[r]
        if not row: continue
        v = _strip(row[0]) if row[0] else ''
        if not v:
            continue
        if any(v.startswith(m) for m in SECTION_MARKERS):
            continue
        if v.startswith('簽章') or v.startswith('註：'):
            break
        parts.append(v)
    return '\n'.join(parts)


def _parse_safety_checks(rows, r_safety, r_sample):
    """抽 R37-R43 內的勤前/勞保/防護具 yes/no。"""
    pre = False
    ins = False
    ppe = False
    other_lines = []
    for r in range(r_safety + 1, min(r_sample or (r_safety + 7), len(rows))):
        row = rows[r]
        if not row: continue
        # all cells combined
        cells_text = ' '.join(str(c).strip() for c in row if c is not None and str(c).strip())
        if not cells_text:
            continue
        if '勤前教育' in cells_text:
            pre = _tick(cells_text)
        elif '勞工保險' in cells_text or '新進勞工' in cells_text:
            ins = _tick_with_no_new(cells_text)
        elif '防護具' in cells_text:
            ppe = _tick(cells_text)
        elif '(二)其他事項' in cells_text:
            continue
        elif '(一)施工前檢查事項' in cells_text:
            continue
    return pre, ins, ppe


def _tick(text):
    """取 ■ 後第一個字元；沒勾選則 False。"""
    idx = text.find('■')
    if idx < 0:
        return False
    after = text[idx + 1:idx + 2]
    if after == '有': return 'yes'
    if after == '無': return 'no'
    return False


def _tick_with_no_new(text):
    if '■無新進勞工' in text:
        return 'no'
    return _tick(text)


def parse_daily_log_b_xlsx(file_bytes: bytes, filename: str = '') -> dict:
    """解析 B 標每日施工日誌 xlsx，回傳 dict 可直接給 daily.log.sheet.create()。"""
    if not file_bytes:
        raise ValueError(f'檔案 {filename} 內容為空')

    try:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_filelike(BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f'檔案 {filename} 無法開啟：{e}')

    if '日報' not in wb.sheet_names:
        raise ValueError(f'檔案 {filename} 缺少 日報 sheet（現有：{wb.sheet_names[:5]}...）')

    ws = wb.get_sheet_by_name('日報')
    rows = list(ws.to_python())

    # --- 日期 ---
    # B 標 xlsx 的 日報 sheet 常被 cached 成同一天，因此優先用檔名 ROC 日期
    log_date = _parse_roc_from_filename(filename)
    if not log_date:
        if len(rows) > 2 and len(rows[2]) > 9:
            log_date = _excel_serial_to_date(rows[2][9])
            if not log_date and len(rows[2]) > 11:
                log_date = _excel_serial_to_date(rows[2][11])
    if not log_date:
        raise ValueError(f'檔案 {filename} 抓不到日期')

    # --- 天氣 ---
    weather_text = _strip(rows[2][0]) if len(rows) > 2 and rows[2] else ''
    weather_am, weather_pm = _parse_weather_cell(weather_text)

    # --- 實際進度 ---
    actual_progress = 0.0
    if len(rows) > 6 and len(rows[6]) > 10:
        raw = rows[6][10]
        try:
            actual_progress = round(float(raw) * 100, 4) if raw not in (None, '') else 0.0
        except (TypeError, ValueError):
            actual_progress = 0.0

    # --- 段落列 ---
    r_item = _find_row(rows, 5, 25, '一、')
    r_material = _find_row(rows, (r_item or 7) + 1, 30, '二、')
    r_labor = _find_row(rows, (r_material or 20) + 1, 35, '三、')
    r_tech = _find_row(rows, (r_labor or 28) + 1, 40, '四、')
    r_safety = _find_row(rows, (r_tech or 35) + 1, 45, '五、')
    r_sample = _find_row(rows, (r_safety or 37) + 1, 50, '六、')
    r_subco = _find_row(rows, (r_sample or 44) + 1, 55, '七、')
    r_important = _find_row(rows, (r_subco or 48) + 1, 60, '八、')

    # --- line rows (施工項目) ---
    line_rows = []
    if r_item is not None and r_material is not None:
        header_row = r_item + 1  # R8
        for r in range(header_row + 1, r_material):
            if r >= len(rows): break
            row = rows[r]
            if not row: continue
            name = _strip(row[0]) if row else ''
            if not name: continue
            if any(name.startswith(m) for m in SECTION_MARKERS):
                continue
            if '營造業專業工程' in name:
                break
            if len(name) <= 3 and re.match(r'^[A-D]\.?$', name):
                continue
            unit = _strip(row[5]) if len(row) > 5 else ''
            planned_qty = _num(row[6]) if len(row) > 6 else 0.0
            daily_qty = _num(row[8]) if len(row) > 8 else 0.0
            cumulative_qty = _num(row[10]) if len(row) > 10 else 0.0
            note = _strip(row[12]) if len(row) > 12 else ''
            line_rows.append({
                'name': name,
                'unit': unit,
                'planned_qty': planned_qty,
                'daily_qty': daily_qty,
                'cumulative_qty': cumulative_qty,
                'note': note,
            })

    # --- material rows ---
    material_rows = []
    if r_material is not None and r_labor is not None:
        header_row = r_material + 1  # R21
        for r in range(header_row + 1, r_labor):
            if r >= len(rows): break
            row = rows[r]
            if not row: continue
            name = _strip(row[0]) if row else ''
            if not name: continue
            if any(name.startswith(m) for m in SECTION_MARKERS):
                continue
            unit = _strip(row[4]) if len(row) > 4 else ''
            contract_qty = _num(row[5]) if len(row) > 5 else 0.0
            daily_qty = _num(row[7]) if len(row) > 7 else 0.0
            cumulative_qty = _num(row[9]) if len(row) > 9 else 0.0
            note = _strip(row[11]) if len(row) > 11 else ''
            material_rows.append({
                'name': name,
                'unit': unit,
                'contract_qty': contract_qty,
                'daily_qty': daily_qty,
                'cumulative_qty': cumulative_qty,
                'note': note,
            })

    # --- 四、技術士 ---
    has_tech = False
    if r_tech is not None:
        for r in range(r_tech, min(r_tech + 3, len(rows))):
            if r >= len(rows): break
            row_text = ' '.join(str(c).strip() for c in rows[r] if c is not None and str(c).strip())
            if '■有' in row_text:
                has_tech = 'yes'; break
            if '■無' in row_text:
                has_tech = 'no'; break

    # --- 五、安衛 ---
    safety_pre, safety_ins, safety_ppe = False, False, False
    safety_other = ''
    if r_safety is not None:
        safety_pre, safety_ins, safety_ppe = _parse_safety_checks(rows, r_safety, r_sample)
        # 其他事項文字在 R42+ col 2 之後
        for r in range(r_safety + 1, min(r_sample or (r_safety + 8), len(rows))):
            row = rows[r]
            if not row: continue
            row_text = ' '.join(str(c).strip() for c in row if c is not None and str(c).strip())
            if '(二)其他事項' in row_text or '其他事項' in row_text:
                other_start = r + 1
                for rr in range(other_start, min(r_sample or (r_safety + 8), len(rows))):
                    line_text = ' '.join(str(c).strip() for c in rows[rr][2:] if c is not None and str(c).strip())
                    if line_text:
                        safety_other = (safety_other + '\n' + line_text).strip()
                break

    # --- 六 / 七 / 八 ---
    sampling_text = _collect_text(rows, (r_sample or 0) + 1, r_subco or 0)
    subco_text = _collect_text(rows, (r_subco or 0) + 1, r_important or 0)
    important_text = _collect_text(rows, (r_important or 0) + 1, (r_important or 0) + 5)

    return {
        'log_date': log_date,
        'weather_am': weather_am,
        'weather_pm': weather_pm,
        'actual_progress': actual_progress,
        'has_technician_requirement': has_tech or False,
        'safety_pre_work_education': safety_pre or False,
        'safety_labor_insurance_check': safety_ins or False,
        'safety_ppe_check': safety_ppe or False,
        'safety_other_matters': safety_other,
        'sampling_test_record': sampling_text,
        'subcontractor_notification': subco_text,
        'important_matters': important_text,
        'line_rows': line_rows,
        'material_rows': material_rows,
    }
