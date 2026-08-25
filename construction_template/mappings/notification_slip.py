# -*- coding: utf-8 -*-
"""預約式工程施工回報單（通報單）—— 佔位符對照表。

樣板原本內嵌來源專案的 23 項工項清單與該案的實際值（使用工期44天、
「111年度水利建造物檢查缺失項目修復」整段說明），2026-08-05 重做成
一列 `${table:items.*}` 樣板列 + 表頭佔位符。

兩張工作表都要填：sheet1 是通知單表頭、sheet2 是工項明細表。
"""

from ..utils.formatters import money, roc_date

MODEL = 'reservation.notification.slip'
MODE = 'placeholder'

CALENDAR_DAY = '日曆天'


def _days(value):
    return '%s%s' % (value, CALENDAR_DAY) if value else ''


def _qty(value):
    if not value:
        return ''
    return ('%g' % value) if isinstance(value, float) else str(value)


def build_context(slip):
    project = slip.project_id
    return {
        'project.name': project.name or '',
        'project.constructionNo': project.contract_no or '',
        'slipNo': slip.slip_no or slip.slip_number or slip.name or '',
        'compiler': slip.compiler_id.display_name or '',
        'location': slip.location or slip.location_detail or '',
        'surveyDate': roc_date(slip.survey_date),
        'plannedStartDate': roc_date(slip.planned_start_date),
        'actualStartDate': roc_date(slip.actual_start_date),
        'actualEndDate': roc_date(slip.actual_end_date),
        'plannedDuration': _days(slip.planned_duration),
        'actualDuration': _days(slip.actual_duration),
        'overdueDays': _days(slip.overdue_days) or '0%s' % CALENDAR_DAY,
        # 預估：手填優先，沒填才退回明細預估合計。
        # 「本次實作結算金額」一律是明細加總，兩者本來就該相等 ——
        # 手填值與明細不符時，通報單表單上會亮黃色示警（has_estimated_mismatch），
        # 那正是「第1頁表頭」與「第2頁詳細表壹列」會對不起來的訊號。
        'estimatedAmount': money(slip.estimated_amount or slip.planned_total_amount),
        'settlementAmount': money(slip.settlement_amount),
        'designSummary': slip.design_summary or '',
        'completionSummary': slip.completion_summary or '',
        # 彙總（小計）列與手填總價列（如「三 雜項工程費」「八 稅什費」）沒有單價
        # 與數量，單價/數量欄要留白而不是印 0 —— 與來源回報單詳細表的排版一致。
        'items': [{
            'itemNo': line.display_item_no or line.item_no or '',
            'description': line.description or '',
            'unit': line.unit or '',
            'unitPrice': '' if line.is_manual_amount else money(line.unit_price),
            'plannedQty': '' if line.is_manual_amount else _qty(line.planned_qty),
            'plannedAmount': money(line.planned_amount),
            'actualQty': '' if line.is_manual_amount else _qty(line.actual_qty),
            'actualAmount': money(line.actual_amount),
        } for line in slip.detail_line_ids],
    }


def FILENAME(slip):
    return '預約式工程施工回報單_%s_%s.xlsx' % (
        slip.project_id.name or '', slip.slip_no or slip.name or slip.id)
