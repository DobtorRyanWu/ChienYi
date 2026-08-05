# -*- coding: utf-8 -*-
"""公共工程施工日誌 第二聯 完成工程詳細表（營造版）—— 佔位符對照表。

第二聯是工項明細表：一列樣板列（`${table:payItems.*}`）依 daily.log.line 展開。
donePercent / totalPercent 對應本日與累計完成百分率（表尾）。
"""

from ..utils.formatters import roc_date

from .daily_log_c1 import _contractor, _qty

MODEL = 'daily.log.sheet'
MODE = 'placeholder'


def build_context(record):
    project = record.project_id
    return {
        'project.name': project.name or '',
        'project.contractor': _contractor(project),
        'fillInAt': roc_date(record.log_date),
        # 樣板只有一頁；分頁由使用者自行列印處理
        'currentPageNo': 1,
        'totalPageNo': 1,
        'donePercent': _qty(record.daily_actual_progress),
        'totalPercent': _qty(record.actual_progress),
        'payItems': [{
            'fullItemNo': line.item_no or '',
            'description': line.item_name or line.custom_name or '',
            'unit': line.unit or '',
            'quantity': _qty(line.contract_qty),
            'doneQuantity': _qty(line.daily_qty),
            'totalQuantity': _qty(line.cumulative_qty),
            'note': line.issue_description or '',
        } for line in record.line_ids],
    }


def FILENAME(record):
    return '施工日誌第二聯_%s_%s.xlsx' % (record.project_id.name or '', record.log_date or '')
