# -*- coding: utf-8 -*-
"""磺港溪 A 標施工日誌 XLSM 解析器

輸入：上溢營造股份有限公司的「公共工程施工日誌」XLSM 檔案 bytes
輸出：dict 可直接餵給 daily.log.sheet.create()

原始檔案結構（sheet='施工日誌'，50×19）：
    R5  本日天氣 上午 [c4] 下午 [c7]  填報日期 [c14]  (星期) [c16]
    R6  工程名稱 ...  承攬廠商 ...
    R7  核定工期 / 累計工期 / 剩餘工期 / 工期展延
    R8  開工日期 / 完工日期
    R9  預定進度% / 實際進度%
    R10 一、依施工計畫書執行按圖施工概況
    R11 (header) 施工項目 [c1] 單位 [c10] 契約數量 [c12] 本日完成 [c13] 累計完成 [c14] 備註 [c15]
    R12+ data rows
    R17 營造業專業工程特定施工項目（子段，跳過）
    R20 二、工地材料管理概況
    R21 (header) 材料名稱 [c1] 單位 [c7] 契約數量 [c8] 本日使用 [c10] 累計使用 [c12] 備註 [c14]
    R22+ data rows
    R26 三、工地人員及機具（模型無對應子表，跳過）
    R31 四、本日施工項目是否有須依「營造業專業工程特定施工項目」設置技術士
    R32 □有 ■無（勾選）
    R33 五、工地職業安全衛生事項（自由文字）
    R35 六、施工取樣試驗紀錄
    R37 七、通知協力廠商辦理事項
    R39 八、重要事項紀錄
"""

import re
from datetime import date, datetime
from io import BytesIO

import openpyxl


WEATHER_MAP = {
    '晴': 'sunny', '晴天': 'sunny', '晴時多雲': 'sunny',
    '多雲': 'cloudy', '多雲時晴': 'cloudy',
    '陰': 'overcast', '陰天': 'overcast', '多雲時陰': 'overcast',
    '雨': 'rainy', '雨天': 'rainy', '小雨': 'rainy', '下雨': 'rainy', '陣雨': 'rainy',
    '豪雨': 'heavy_rain', '大雨': 'heavy_rain', '暴雨': 'heavy_rain',
    '颱風': 'typhoon',
    '霧': 'foggy', '有霧': 'foggy',
}

# 段落起始標記（用來切 section range）
SECTION_MARKERS = ('一、', '二、', '三、', '四、', '五、', '六、', '七、', '八、', '九、', '十、')


def _map_weather(val):
    if val is None:
        return False
    s = str(val).strip()
    if not s:
        return False
    return WEATHER_MAP.get(s, False)


def _parse_minguo_from_filename(fname):
    """檔名含 '1121003' 之類民國年格式 → date(2023, 10, 3)

    優先抓 `截止至(\\d{7})` 後再抓獨立 `(\\d{7})`。
    """
    if not fname:
        return None
    m = re.search(r'截止至(\d{7})', fname)
    if not m:
        m = re.search(r'(\d{7})', fname)
    if not m:
        return None
    raw = m.group(1)
    try:
        year = int(raw[:3]) + 1911
        month = int(raw[3:5])
        day = int(raw[5:7])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def _cell(ws, r, c):
    try:
        return ws.cell(row=r, column=c).value
    except Exception:
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


def _find_section_row(ws, prefix, max_row=60):
    """找 col 1 以 prefix 開頭的列，回傳列號（1-based）。"""
    for r in range(1, max_row + 1):
        v = _strip(_cell(ws, r, 1))
        if v.startswith(prefix):
            return r
    return None


_FOOTER_STOP_MARKERS = ('簽章', '註：', '註:', '依營造業法')


def _parse_safety_checks(text):
    """從 R33 整格文字抽出三個勤前檢查的 yes/no。

    R33 文字範例：
        五、工地職業安全衛生事項...
         (一)施工前檢查事項：
          1.實施勤前教育(含...):■有  □無
          2.確認新進勞工...：□有  □無  ■無新進勞工
          3.檢查勞工個人防護具：■有  □無
         (二)其他事項：(可能有內容)

    規則：每一項找 ■ 後面第一個非空字元：
        - ■有 → 'yes'
        - ■無 → 'no'
    勞保那一題多一個框「■無新進勞工」→ 'no_new_worker'（本項不適用，語意與「無」相反）
    找不到打勾 → False
    """
    if not text:
        return False, False, False, ''

    # 拆成 lines
    lines = [l.strip() for l in text.split('\n')]

    def _tick(line):
        """取 ■ 後第一個字元判斷 yes/no"""
        idx = line.find('■')
        if idx < 0:
            return False
        after = line[idx + 1:idx + 2]
        if after == '有':
            return 'yes'
        if after == '無':
            return 'no'
        return False

    def _tick_labor(line):
        """勞保這一題專用：先判「無新進勞工」

        整行第一個 ■ 落在「■無新進勞工」時，_tick() 只看 ■ 的下一個字（「無」）
        會誤判成 'no'。比對前去掉空白，避免「■ 無新進勞工」這種變體漏掉。
        """
        if '■無新進勞工' in re.sub(r'\s', '', line or ''):
            return 'no_new_worker'
        return _tick(line)

    pre_edu = False
    labor_ins = False
    ppe = False

    for line in lines:
        if '勤前教育' in line:
            pre_edu = _tick(line)
        elif '勞工保險' in line or '新進勞工' in line:
            labor_ins = _tick_labor(line)
        elif '防護具' in line:
            ppe = _tick(line)

    # 抽 (二)其他事項： 後面的內容
    other_text = ''
    marker = '(二)其他事項：'
    idx = text.find(marker)
    if idx >= 0:
        other_text = text[idx + len(marker):].strip()

    return pre_edu, labor_ins, ppe, other_text


def _collect_text(ws, start_row, end_row, skip_markers=True):
    """把 [start_row, end_row) 範圍內 col 1 的非空文字串起來。

    - skip_markers=True 時，跳過本身是段落 header 的那一列（避免 '五、...' 被收進來）
    - 遇到 footer marker（簽章 / 註： / ...）即停止，避免把固定格式文字當成內容
    """
    if not start_row or not end_row or start_row >= end_row:
        return ''
    parts = []
    for r in range(start_row, end_row):
        v = _strip(_cell(ws, r, 1))
        if not v:
            continue
        if skip_markers and any(v.startswith(m) for m in SECTION_MARKERS):
            continue
        if any(v.startswith(fm) for fm in _FOOTER_STOP_MARKERS):
            break
        parts.append(v)
    return '\n'.join(parts)


def parse_daily_log_xlsm(file_bytes: bytes, filename: str = '') -> dict:
    """解析一份施工日誌 XLSM，回傳 dict。

    可能 raise ValueError：缺少必要 sheet、抓不到日期等。
    """
    if not file_bytes:
        raise ValueError(f'檔案 {filename} 內容為空')

    try:
        wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True, read_only=False)
    except Exception as e:
        raise ValueError(f'檔案 {filename} 無法開啟：{e}')

    if '施工日誌' not in wb.sheetnames:
        raise ValueError(
            f'檔案 {filename} 缺少「施工日誌」sheet（現有：{wb.sheetnames}）'
        )
    ws = wb['施工日誌']

    # ---- 日期 ----
    raw_date = _cell(ws, 5, 14)
    log_date = None
    if isinstance(raw_date, datetime):
        log_date = raw_date.date()
    elif isinstance(raw_date, date):
        log_date = raw_date
    if not log_date:
        log_date = _parse_minguo_from_filename(filename)
    if not log_date:
        raise ValueError(f'檔案 {filename} 抓不到日期（R5c14 空且檔名無民國年）')

    # ---- 天氣 ----
    weather_am = _map_weather(_cell(ws, 5, 4))
    weather_pm = _map_weather(_cell(ws, 5, 7))

    # ---- 實際進度（R9 C14，原值為小數 0.0407 = 4.07%） ----
    raw_actual = _cell(ws, 9, 14)
    actual_progress = 0.0
    if raw_actual not in (None, ''):
        try:
            actual_progress = round(float(raw_actual) * 100, 4)
        except (TypeError, ValueError):
            actual_progress = 0.0

    # ---- 段落列號 ----
    r_item = _find_section_row(ws, '一、')
    r_material = _find_section_row(ws, '二、')
    r_labor = _find_section_row(ws, '三、')
    r_tech = _find_section_row(ws, '四、')
    r_safety = _find_section_row(ws, '五、')
    r_sample = _find_section_row(ws, '六、')
    r_subco = _find_section_row(ws, '七、')
    r_important = _find_section_row(ws, '八、')

    # ---- 施工項目（line_rows） ----
    line_rows = []
    if r_item and r_material:
        # R11 是 header（含「施工項目 / 單位 / 契約數量 ...」），data 從 R12 起
        header_row = r_item + 1
        for r in range(header_row + 1, r_material):
            name = _strip(_cell(ws, r, 1))
            if not name:
                continue
            if any(name.startswith(m) for m in SECTION_MARKERS):
                continue
            # 「營造業專業工程特定施工項目」是嵌入的子段落 header，從此處中斷
            if '營造業專業工程' in name:
                break
            # A / B / C 子項（子清單，非工項資料）
            if len(name) <= 2 and name.upper() in ('A', 'B', 'C', 'D'):
                continue
            unit = _strip(_cell(ws, r, 10))
            planned_qty = _num(_cell(ws, r, 12))
            daily_qty = _num(_cell(ws, r, 13))
            cumulative_qty = _num(_cell(ws, r, 14))
            note = _strip(_cell(ws, r, 15))
            line_rows.append({
                'name': name,
                'unit': unit,
                'planned_qty': planned_qty,
                'daily_qty': daily_qty,
                'cumulative_qty': cumulative_qty,
                'note': note,
            })

    # ---- 工地材料（material_rows） ----
    material_rows = []
    if r_material and r_labor:
        header_row = r_material + 1
        for r in range(header_row + 1, r_labor):
            name = _strip(_cell(ws, r, 1))
            if not name:
                continue
            if any(name.startswith(m) for m in SECTION_MARKERS):
                continue
            unit = _strip(_cell(ws, r, 7))
            contract_qty = _num(_cell(ws, r, 8))
            daily_qty = _num(_cell(ws, r, 10))
            cumulative_qty = _num(_cell(ws, r, 12))
            note = _strip(_cell(ws, r, 14))
            material_rows.append({
                'name': name,
                'unit': unit,
                'contract_qty': contract_qty,
                'daily_qty': daily_qty,
                'cumulative_qty': cumulative_qty,
                'note': note,
            })

    # ---- 技術士要求（R31-R32 的 ■有/■無） ----
    has_technician = False
    if r_tech:
        for r in range(r_tech, min(r_tech + 4, r_safety or r_tech + 4)):
            for c in range(1, 20):
                v = _strip(_cell(ws, r, c))
                if '■有' in v:
                    has_technician = 'yes'
                    break
                if '■無' in v:
                    has_technician = 'no'
                    break
            if has_technician:
                break

    # ---- 五、工地職業安全衛生事項 ----
    # R33 整格內含三個勤前檢查 ■有/■無 與 (二)其他事項：
    safety_raw = _strip(_cell(ws, r_safety, 1)) if r_safety else ''
    safety_pre_edu, safety_labor_ins, safety_ppe, safety_other_inline = _parse_safety_checks(safety_raw)

    # R33 之後到 R35 之間如果有額外文字列，補進 其他事項
    safety_trailing = _collect_text(ws, (r_safety or 0) + 1, r_sample or 0)
    safety_text_parts = [p for p in (safety_other_inline, safety_trailing) if p]
    safety_text = '\n'.join(safety_text_parts)

    # ---- 其他文字段落 ----
    sampling_text = _collect_text(ws, (r_sample or 0) + 1, r_subco or 0)
    subco_text = _collect_text(ws, (r_subco or 0) + 1, r_important or 0)
    important_text = _collect_text(ws, (r_important or 0) + 1, (r_important or 0) + 6)

    return {
        'log_date': log_date,
        'weather_am': weather_am,
        'weather_pm': weather_pm,
        'actual_progress': actual_progress,
        'has_technician_requirement': has_technician or False,
        'safety_pre_work_education': safety_pre_edu or False,
        'safety_labor_insurance_check': safety_labor_ins or False,
        'safety_ppe_check': safety_ppe or False,
        'safety_other_matters': safety_text,
        'sampling_test_record': sampling_text,
        'subcontractor_notification': subco_text,
        'important_matters': important_text,
        'line_rows': line_rows,
        'material_rows': material_rows,
    }
