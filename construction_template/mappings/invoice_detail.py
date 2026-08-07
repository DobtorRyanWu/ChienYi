# -*- coding: utf-8 -*-
"""估驗詳細表（估驗總表）—— 佔位符對照表。

樣板 = EAGLE 的全域 `invoiceTemplate.xlsx`（不是專案層級樣板，config 裡是
固定 URL `PUBLIC_INVOICE_TEMPLATE_URL`）。EAGLE 把它與「估驗照片.docx」
打包成 zip 一起下載（`models/project.js / generateInvoiceFile()`）；
Odoo 這邊拆成兩個按鈕，各自下載。

欄位語意直接取自樣板第 4~6 列的表頭：

    (一) 契約數量  (二) 變更後核定數量  (三) 單價  (四) 本次估驗數量
    (五) 本次止累計估驗數量  (六) 本次估驗金額  (七) 本次止累計估驗金額

## 對原樣板做的一處修正

原樣板 D7 與 E7 **共用同一個佔位符** `${table:payItems.quantity}`，
所以「變更後核定數量」欄印出來的其實是契約數量——欄位標題與內容不符。
2026-08-06 把 E7 改成 `${table:payItems.approvedQuantity}`（inlineStr，
不動 sharedStrings 以免 D7 跟著變），其餘 zip entry 位元組完全未動。
"""

from ..utils.formatters import roc_date_cn

from .progress_report import authority_name, estimate_warnings

MODEL = 'payment.estimate'
MODE = 'placeholder'

# 「本次止累計估驗數量／金額」兩欄跟進度報告的累計是同一個計算來源，
# 前期估驗沒核定就會低估——共用同一組警示。
WARNINGS = estimate_warnings


def _num(value):
    """數量／金額：0 與空值印空白，避免整張表都是 0"""
    if not value:
        return ''
    return '%g' % value if isinstance(value, float) else str(value)


def _money(value):
    """金額保留兩位小數——對應 EAGLE 的 `(qty * price).toFixed(2)`"""
    if not value:
        return ''
    return '%.2f' % value


def _amount(line, qty_field, amount_field):
    """金額優先用模型算好的欄位，取不到才回退「數量 × 單價」。

    實查 odoo18_dev：unit_price 只有 1882/13796 筆有值，
    純用「數量 × 單價」會讓多數明細的金額欄空白。
    """
    stored = line[amount_field]
    if stored:
        return stored
    return line[qty_field] * line.unit_price


def build_context(estimate):
    lines = estimate.line_ids.sorted(lambda ln: (ln.sequence, ln.id))
    return {
        # 抬頭的業主機關：原樣板寫死「臺北市政府工務局水利工程處」，
        # 2026-08-07 改成佔位符，接工程案件既有的 authority_name 欄位。
        'authorityName': authority_name(estimate.project_id),
        'times': estimate.estimate_no or '',
        'projectName': estimate.project_id.name or '',
        # EAGLE：`${y-1911}年${m}月${d}日`
        'date': roc_date_cn(estimate.estimate_date),
        'payItems': [{
            'fullItemNo': line.item_no or '',
            'description': line.description or '',
            'unit': line.unit or '',
            'quantity': _num(line.contract_qty),
            'approvedQuantity': _num(line.approved_qty or line.contract_qty),
            'price': _money(line.unit_price),
            'sumQuantity': _num(line.estimate_qty),
            'totalQuantity': _num(line.cumulative_estimate_qty),
            'sumAmount': _money(_amount(line, 'estimate_qty', 'estimate_amount')),
            'totalAmount': _money(_amount(
                line, 'cumulative_estimate_qty', 'cumulative_estimate_amount')),
            'note': line.note or '',
        } for line in lines],
    }


def FILENAME(estimate):
    return '估驗詳細表_%s_第%s次.xlsx' % (
        estimate.project_id.name or '', estimate.estimate_no or 0)
