# -*- coding: utf-8 -*-
"""公共工程監造日報表 第一聯 —— 儲存格對照表。

座標來自 data/templates_blank/daily_log_1.xlsx 的實際版面（工作表「第一聯」，
A3:L44、104 個合併範圍）。**值一律填合併範圍的左上角那一格**，填錯格子在
Excel 畫面上看不出來，但列印會缺。

版面（左為標籤格，右為值格）：
    A5  本日天氣:上午 → B5        C5  下午 → D5        G5:H5 填報日期 → I5
    A6  工程名稱 → B6             I6:J6 契約編號 → K6
    A7  主辦機關 → B7             D7 契約工期 → E7      F7 開工日期 → G7
    H7  預定竣工日期 → I7          K7 實際竣工日期 → L7
    A9  契約變更次數 → C9          E9 工期展延天數 → G9
    H9  契約金額：I9 原契約 → K9 ／ I10 變更後契約 → K10
    A10 預定進度(%) → C10          E10 實際進度(%) → G10
    A12 一、工程進行情況 → 明細表 A13:E16 + 大文字區 F13
    A17 本日重要工作（A17:L19）
    A26 三、查核材料 → 明細表 A28:L32（5 列）
    A35 （二）其他工地安全衛生督導事項 → A36
    A37 五、其他約定監造事項 → A38
"""

MODEL = 'daily.log.sheet'
SHEET = 'xl/worksheets/sheet1.xml'

CELLS = {
    # 表頭
    'B5': ('weather_am', 'selection_label'),
    'D5': ('weather_pm', 'selection_label'),
    'I5': ('log_date', 'roc_date'),
    'B6': 'project_id.name',
    'K6': 'project_id.contract_no',
    'B7': 'project_id.partner_id.name',
    'E7': 'project_id.contract_duration',
    'G7': ('project_id.contract_start_date', 'roc_date'),
    'I7': ('project_id.contract_end_date', 'roc_date'),
    # L7 實際竣工日期：project.project 沒有對應欄位，留空由人工填

    # 契約與進度
    'C9': ('project_id.change_order_ids', 'count'),
    'G9': 'project_id.extension_duration',
    'K9': ('project_id.original_contract_amount', 'money'),
    'K10': ('project_id.current_contract_amount', 'money'),
    'C10': ('daily_planned_progress', 'percent'),
    'G10': ('actual_progress', 'percent'),

    # 文字區
    'F13': 'work_summary',            # 一、工程進行情況（F13:L16，無標籤）
    # A17:L19 的「本日重要工作：」是表單本文不是資料，要保留；
    # 空白樣板裡它後面還跟著來源文件殘留的「1.假日自行車多，無施工。」，
    # 套印時一併蓋掉（殘料本身建議另外從樣板檔清掉）。
    'A17': lambda rec: '本日重要工作：%s' % (rec.important_matters or ''),
    'A36': 'safety_other_matters',    # （二）其他工地安全衛生督導事項
    'A38': 'notes',                   # 五、其他約定監造事項（A38:L41）
}

ROWS = [
    {
        # 一、工程進行情況的施工項目明細（A13:B16 項目 / C13:E16 數量）
        'source': 'line_ids',
        'start_row': 13,
        'max_rows': 4,
        'columns': {
            'A': lambda line: line.item_name or line.custom_name or '',
            'C': lambda line: (
                '%s %s' % (line.daily_qty, line.unit or '') if line.daily_qty else ''),
        },
    },
    {
        # 三、查核材料規格及品質（A28:L32，樣板預留 5 列）
        # C 取樣位置 / H 試樣數量 / I 設計強度 在 daily.log.material 沒有對應欄位，
        # 留空由人工填，不硬湊。
        'source': 'material_ids',
        'start_row': 28,
        'max_rows': 5,
        'columns': {
            'A': 'name',
            'F': lambda line: (
                '%s %s' % (line.daily_qty, line.unit or '') if line.daily_qty else ''),
            'K': 'note',
        },
    },
]


def FILENAME(record):
    return '監造日報表第一聯_%s_%s.xlsx' % (
        record.project_id.name or '', record.log_date or '')
