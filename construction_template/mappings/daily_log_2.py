# -*- coding: utf-8 -*-
"""公共工程監造日報表 第二聯 完成工程詳細表（監造版）—— 佔位符對照表。

樣板原本內嵌來源專案整棵工項樹（456 列固定清單）＋該案的實際進度「累計91%」，
2026-08-05 重做成一列 `${table:payItems.*}` 樣板列，依專案的 daily.log.line
動態展開——每個專案的工項本來就不同，固定清單無法共用。

欄位與營造版第二聯（daily_log_c2）相同，差別只在表頭少了承攬廠商與頁碼，
所以直接沿用那邊的取值邏輯。
"""

from ..utils.formatters import roc_date

from .daily_log_c1 import _qty

MODEL = 'daily.log.sheet'
MODE = 'placeholder'


def build_context(record):
    return {
        'project.name': record.project_id.name or '',
        'fillInAt': roc_date(record.log_date),
        'donePercent': _qty(record.daily_actual_progress),
        'totalPercent': _qty(record.actual_progress),
        'payItems': [{
            'description': line.item_name or line.custom_name or '',
            'unit': line.unit or '',
            'quantity': _qty(line.contract_qty),
            'doneQuantity': _qty(line.daily_qty),
            'totalQuantity': _qty(line.cumulative_qty),
            'note': line.issue_description or '',
        } for line in record.line_ids],
    }


def FILENAME(record):
    return '監造日報表第二聯_%s_%s.xlsx' % (
        record.project_id.name or '', record.log_date or '')
