# -*- coding: utf-8 -*-
"""公共工程施工日誌 第一聯（營造版）—— 佔位符對照表。

樣板本身內建 `${token}` 佔位符，來自舊 EAGLE 系統。token 名稱與 EAGLE
`dailyRecord` collection 的欄位一對一（2026-08-05 以 migrate_synology 的
BSON dump 實測比對，16 個 token 有 14 個直接命中欄位名）。

    token                   EAGLE 欄位            Odoo daily.log.sheet
    ─────────────────────────────────────────────────────────────────
    value1 核定工期          value1               total_approved_duration
    value2 累計工期          value2               cumulative_duration
    value3 剩餘工期          value3               remaining_duration
    value4 工期展延天數      value4               extension_duration
    expectProgress          expectProgress       daily_planned_progress
    exportProgress          exportProgress       actual_progress
    fillInAt                fillInAt             log_date
    fillInAtDay             （衍生）              log_date 的星期
    serialNo                serialNo             name
    constructionSample      constructionSample   sampling_test_record
    subConstructorHandle    subConstructorHandle subcontractor_notification
    important               important            important_matters
    other                   other                safety_other_matters
    manUsage / machineUsage manMachineUsage 拆分  man_machine_detail_ids
                                                 （record_type personnel/equipment）
"""

from ..utils.formatters import roc_date, selection_label

MODEL = 'daily.log.sheet'
MODE = 'placeholder'

WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']


def _qty(value, unit=None):
    """數量：0 與空值都印空白，避免整張表都是 0"""
    if not value:
        return ''
    text = ('%g' % value) if isinstance(value, float) else str(value)
    return '%s %s' % (text, unit) if unit else text


def _contractor(project):
    """承攬廠商名稱——取專案的承攬廠商，多家以頓號相連"""
    partners = project.contractor_partner_ids
    return '、'.join(partners.mapped('name')) if partners else ''


def _work_items(record):
    """一、施工項目的列資料（一般式與預約式共用，見 build_context 的說明）"""
    return [{
        'description': line.item_name or line.custom_name or '',
        'unit': line.unit or '',
        'quantity': _qty(line.contract_qty),
        'doneQuantity': _qty(line.daily_qty),
        'totalQuantity': _qty(line.cumulative_qty),
        'note': line.issue_description or '',
    } for line in record.line_ids]


def _weather(record):
    """本日天氣：上午/下午合併成一格"""
    am = selection_label(record.weather_am, record, 'weather_am')
    pm = selection_label(record.weather_pm, record, 'weather_pm')
    if am and pm:
        return '上午 %s／下午 %s' % (am, pm)
    return am or pm or ''


def build_context(record):
    project = record.project_id
    details = record.man_machine_detail_ids

    return {
        # 表頭
        'project.contractor': _contractor(project),
        'project.name': project.name or '',
        'project.beginAt': roc_date(project.contract_start_date),
        'project.finishAt': roc_date(project.contract_end_date),
        'serialNo': record.name or '',
        'weather': _weather(record),
        'fillInAt': roc_date(record.log_date),
        'fillInAtDay': WEEKDAYS[record.log_date.weekday()] if record.log_date else '',

        # 工期與進度
        'value1': _qty(record.total_approved_duration),
        'value2': _qty(record.cumulative_duration),
        'value3': _qty(record.remaining_duration),
        'value4': _qty(record.extension_duration),
        'expectProgress': _qty(record.daily_planned_progress),
        'exportProgress': _qty(record.actual_progress),

        # 文字區
        'other': record.safety_other_matters or '',
        'constructionSample': record.sampling_test_record or '',
        'subConstructorHandle': record.subcontractor_notification or '',
        'important': record.important_matters or '',

        # 一、施工項目
        #
        # ⚠️ 集合名要給兩個。EAGLE 的第一聯有一般式與預約式兩份樣板，除了這一列
        # 的集合名之外**完全相同**（2026-08-06 逐格比對：45 個 token 中只有這 6 個
        # 不一樣，其餘 39 個含 specificConstructionItems / materialItems / manUsage /
        # machineUsage 全都一致）：
        #     一般式 default.xlsx             ${table:constructionItems.*}  取契約工項
        #     預約式 default_appointment.xlsx ${table:projectSheets.*}      取通報單工項
        # Odoo 這邊兩者都是 daily.log.sheet.line_ids，資料同源，所以兩個鍵指向同一份
        # 列資料——系統預設樣板放一般式版，專案若自行上傳預約式版也照樣填得進去。
        'constructionItems': _work_items(record),
        'projectSheets': _work_items(record),

        # 營造業專業工程特定施工項目：Odoo 目前沒有對應資料來源，
        # 留空讓表格保持一列空白（不硬湊）
        'specificConstructionItems': [],

        # 二、工地材料管理
        'materialItems': [{
            'description': mat.name or '',
            'unit': mat.unit or '',
            'quantity': _qty(mat.contract_qty),
            'doneQuantity': _qty(mat.daily_qty),
            'totalQuantity': _qty(mat.cumulative_qty),
            'note': mat.note or '',
        } for mat in record.material_ids],

        # 三、工地人員（左半）與機具（右半）——同一列兩個集合，各自獨立索引
        'manUsage': [{
            'description': d.personnel_type_id.display_name or d.employee_name or '',
            'doneQuantity': _qty(d.quantity),
            'totalQuantity': _qty(d.hours),
        } for d in details.filtered(lambda d: d.record_type == 'personnel')],

        'machineUsage': [{
            'description': d.specific_equipment_name or d.man_machine_id.display_name or '',
            'doneQuantity': _qty(d.quantity),
            'totalQuantity': _qty(d.hours),
        } for d in details.filtered(lambda d: d.record_type == 'equipment')],
    }


def FILENAME(record):
    return '施工日誌第一聯_%s_%s.xlsx' % (record.project_id.name or '', record.log_date or '')
