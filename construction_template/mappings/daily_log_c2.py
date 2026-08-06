# -*- coding: utf-8 -*-
"""公共工程施工日誌 第二聯 完成工程詳細表（營造版）—— 佔位符對照表。

規格取自 EAGLE 原系統 `models/dailyRecord.js / generateDailyPayItemFile()`
（2026-08-06 由 TKU source map 還原）：

    const totalPageNo = Math.floor(data.payItems.length / 30) + 1
    for (currentPageNo = 1..totalPageNo) {
      copySheet(`第${n}頁`, `第${n+1}頁`)
      payItems = 本頁 30 筆（最後一頁取剩下的）
      while (payItems.length < 30) payItems.push({ description: ' ' })
      substitute(currentPageNo, {
        totalPercent: 最後一頁 ? exportProgress/100 : undefined,
        donePercent:  最後一頁 ? progress/100      : undefined,
        totalPageNo: `第${totalPageNo}頁`, currentPageNo: `第${n}頁`, payItems })
    }

三個先前做錯的地方（已修正）：
  ① 沒有分頁 → 現在每頁 30 列、不足補空白列
  ② 頁碼給整數 → 原系統是**字串**「第N頁」
  ③ 百分比直接給格式化數字且每頁都給 → 原系統是**除以 100**
     （儲存格本身是百分比格式）且**只在最後一頁**給值
"""

from ..utils.formatters import roc_date

from .daily_log_c1 import _contractor, _qty

MODEL = 'daily.log.sheet'
MODE = 'placeholder'

ROWS_PER_PAGE = 30

PAGINATE = {
    'source': 'payItems',
    'page_size': ROWS_PER_PAGE,
    # 不足補空白列：原系統補 {description: ' '}，一個空白字元讓儲存格保有框線
    'pad': {'description': ' '},
    # 這兩個只在最後一頁給值（其餘頁留白）
    'last_page_only': ('donePercent', 'totalPercent'),
}


def _percent(value):
    """儲存格是百分比格式，所以要給 0~1 的小數而不是 0~100"""
    return (value or 0) / 100.0


def build_context(record):
    project = record.project_id
    return {
        'project.name': project.name or '',
        'project.contractor': _contractor(project),
        'fillInAt': roc_date(record.log_date),
        # currentPageNo / totalPageNo 由引擎依實際頁數填入「第N頁」
        'donePercent': _percent(record.daily_actual_progress),
        'totalPercent': _percent(record.actual_progress),
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
