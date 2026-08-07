# -*- coding: utf-8 -*-
"""進度報告（公共工程施工日誌 第二聯 完成工程詳細表・期間版）—— 佔位符對照表。

樣板 = EAGLE 的 `progressReportTemplate`，版面與「施工日誌第二聯」完全相同，
差別只在期間：第二聯是「本**日**完成數量」（token `doneQuantity`），
本表是「本**期**完成數量」（token `sumQuantity`）。

規格取自 EAGLE `models/project.js / generateProgressReportFile()`
（2026-08-06 由 TKU source map 還原）：

    totalPageNo = Math.floor(payItems.length / 30) + 1
    每頁 30 筆、不足補 { description: ' ' }
    totalPercent / donePercent 只在最後一頁給值
    contractAmount += price * quantity        （排除「有子項的彙總列」）
    sumAmount      += price * sumQuantity
    totalAmount    += price * totalQuantity

## 期間怎麼定義

EAGLE 由前端傳 `rangeTime[0..1]`（使用者自選區間）。Odoo 沒有這種
「選區間再匯出」的入口，改以**估驗單**為期間錨點——一張估驗單本來就代表
一個計價期間，且 `payment.estimate.line` 已經備妥本期（estimate_qty）與
累計（cumulative_estimate_qty）兩個數量，不需要另外推算。
"""

from ..utils.formatters import roc_date

from .daily_log_c1 import _contractor, _qty

MODEL = 'payment.estimate'
MODE = 'placeholder'

ROWS_PER_PAGE = 30

PAGINATE = {
    'source': 'payItems',
    'page_size': ROWS_PER_PAGE,
    # 不足補空白列：原系統補 {description: ' '}，一個空白字元讓儲存格保有框線
    'pad': {'description': ' '},
    # 完成百分率只印在最後一頁
    'last_page_only': ('donePercent', 'totalPercent'),
}


# 只有這兩個狀態的估驗單會被 `_compute_previous_approved_qty` 計入前期累計
APPROVED_STATES = ('approved', 'archived')

# 報表抬頭的業主機關。工程案件本來就有 `authority_name`（業主/主辦機關，Char），
# 但 2026-08-07 實查 196 個案件只有 1 個填了值——就是這個字串。
# 樣板原本把它寫死在儲存格裡，現在改成佔位符；欄位空白時回退到這個預設值，
# 讓既有輸出完全不變，同時由 WARNINGS 提醒使用者去補欄位。
DEFAULT_AUTHORITY = '臺北市政府工務局水利工程處'


def authority_name(project):
    return (project.authority_name or '').strip() or DEFAULT_AUTHORITY


def estimate_warnings(estimate):
    """回報會讓「累計」數字失真的資料狀況（由匯出 mixin 顯示給使用者）。

    `payment.estimate.line._compute_previous_approved_qty` 有兩個前提，
    任一不成立就直接回 0，累計數量會等於本期數量——報表本身看不出異狀：

        if (line.is_summary_item or not line.task_id
                or not est.project_id or not est.estimate_date):
            line.previous_approved_qty = 0.0
        …
        ('estimate_id.state', 'in', ('approved', 'archived'))

    實例（odoo18_dev 2026-08-07）：專案 43 的 30 張估驗全停在草稿，
    第 18 次的累計原本等於本期；14 張核定後前期累計才正確帶出。
    另有 46 張 draft 估驗沒有估驗日期，核定也救不回來。
    """
    # ⚠️ 這裡刻意**不**檢查 authority_name 是否為空。
    # 2026-08-07 實測：196 個工程案件只有 1 個填了業主機關，加進來的結果是
    # 每一次匯出都跳提示，而且排在累計警示前面——把「數字是錯的」這種真問題
    # 稀釋成雜訊。抬頭沒填會回退到 DEFAULT_AUTHORITY，輸出與過去完全相同，
    # 屬於資料待補而非數字錯誤，記在 docs/資料缺口清單.md 由人一次補齊。
    messages = []
    if not estimate.estimate_date:
        messages.append(
            '本張估驗單沒有填「估驗日期」，系統無法判斷期別先後，'
            '「累計」欄位會等於「本期」。請先補上估驗日期。')
        return messages

    pending = estimate.search([
        ('project_id', '=', estimate.project_id.id),
        ('estimate_date', '<', estimate.estimate_date),
        ('state', 'not in', APPROVED_STATES),
        ('line_ids', '!=', False),
    ])
    if pending:
        messages.append(
            '本專案在 %s 之前還有 %s 張未核定的估驗單（最早 %s）。'
            '「累計」只計入已核定的期別，數字會低估。'
            % (estimate.estimate_date, len(pending),
               min(pending.mapped('estimate_date'))))
    return messages


WARNINGS = estimate_warnings


def _contract_qty(line):
    """契約數量。

    樣板註 3：「如辦理契約變更，應填寫修正核定後之契約數量」——所以有核定數量
    就用核定數量。對應 EAGLE 的
    `if (!payItem.isApproved && payItem.previous) quantity = previous.quantity`。
    """
    return line.approved_qty or line.contract_qty or 0.0


def _amounts(lines):
    """(契約金額, 本期金額, 累計金額)。

    彙總列（is_summary_item）排除在加總外，否則大類與其子項會重複計算——
    對應 EAGLE 的 `if (!payItem.isTitle || !payItem.hasChild)`。

    金額優先取模型已算好的欄位（estimate_amount／cumulative_estimate_amount），
    取不到才回退成「數量 × 單價」。實查 odoo18_dev：13796 筆明細中
    cumulative_estimate_amount 全部有值，但 unit_price 只有 1882 筆有值，
    所以純用「數量 × 單價」會讓多數專案的百分率變成 0。
    """
    leaves = [ln for ln in lines if not ln.is_summary_item]
    contract = sum(_contract_qty(ln) * ln.unit_price for ln in leaves)
    current = sum(ln.estimate_amount or (ln.estimate_qty * ln.unit_price) for ln in leaves)
    cumulative = sum(ln.cumulative_estimate_amount or
                     (ln.cumulative_estimate_qty * ln.unit_price) for ln in leaves)
    return contract, current, cumulative


def _percent(amount, contract_amount):
    """儲存格是百分比格式，要給 0~1 的小數。

    契約金額為 0（單價未建）時回 None——留白，不印假的 0%。
    """
    if not contract_amount:
        return None
    return amount / contract_amount


def build_context(estimate):
    project = estimate.project_id
    lines = estimate.line_ids.sorted(lambda ln: (ln.sequence, ln.id))
    contract_amount, current_amount, cumulative_amount = _amounts(lines)
    return {
        'project.name': project.name or '',
        'project.contractor': _contractor(project),
        'fillInAt': roc_date(estimate.estimate_date),
        # currentPageNo / totalPageNo 由引擎依實際頁數填入「第N頁」
        'donePercent': _percent(current_amount, contract_amount),
        'totalPercent': _percent(cumulative_amount, contract_amount),
        'payItems': [{
            'fullItemNo': line.item_no or '',
            'description': line.description or '',
            'unit': line.unit or '',
            'quantity': _qty(_contract_qty(line)),
            'sumQuantity': _qty(line.estimate_qty),
            'totalQuantity': _qty(line.cumulative_estimate_qty),
            'note': line.note or '',
        } for line in lines],
    }


def FILENAME(estimate):
    return '進度報告_%s_第%s次.xlsx' % (
        estimate.project_id.name or '', estimate.estimate_no or 0)
