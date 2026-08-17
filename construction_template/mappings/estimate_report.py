# -*- coding: utf-8 -*-
"""工程估驗計價單 —— 佔位符對照表。

樣板原本內嵌來源專案的值（日曆天270天／臺北市／工務科北區工務所／
第1次估驗，第1次付款）與 3 個未引用的殘留字串（真實契約編號與金額），
2026-08-05 重做成佔位符 + 一列 `${table:categories.*}` 明細樣板列。

明細區印的是**彙總列**（is_summary_item，實際每張 6~18 個大類），
原本的 7 列固定列不夠用，所以改成動態展開。

## 沒有資料來源的欄位（留白由人工填）

會計科目、承辦工務所、已工作日數、本期核發／應扣／實發金額、
以前核發金額、總計核發金額、各大類的保留金額與核發金額
——payment.estimate 沒有這些欄位，硬湊會產生假數字。
"""

from ..utils.formatters import contractor_name, money, roc_date

MODEL = 'payment.estimate'
MODE = 'placeholder'

# 保留款比率：全系統沒有這個欄位（只有 payment.claim.retention_amount 是金額）。
# 原樣板把 5% 寫死在儲存格裡，這裡改成具名常數——公共工程慣例是 5%，
# 但**契約不同就要改**，之後若模型補上欄位應改讀該欄位。
DEFAULT_RETENTION_RATE = 5


def _pct(part, whole):
    return '%.2f' % (part / whole * 100) if whole else ''


def _children_of(category, all_lines):
    """該大類底下的所有葉節點。

    層級靠 item_no 的點號前綴表示（1 → 1.(一) → 1.(一).1），
    比對 parent_item_name 字串（"1.(一) 整備工程"）脆弱得多，所以用前綴。
    """
    prefix = '%s.' % (category.item_no or '')
    return all_lines.filtered(
        lambda x: not x.is_summary_item and (x.item_no or '').startswith(prefix))


def _category(category, all_lines):
    """明細大類一列。

    彙總列本身不帶金額（實測 contract_qty / unit_price / estimate_amount 都是 0），
    數字在子項上，所以要往下加總——否則整張表印出來全是 0。
    保留金額與核發金額模型沒有對應欄位，留白由人工填。
    """
    children = _children_of(category, all_lines)
    contract = sum((c.contract_qty or 0) * (c.unit_price or 0) for c in children)
    current = sum(c.estimate_amount or 0 for c in children)
    return {
        'name': category.description or category.item_no or '',
        'contractAmount': money(contract),
        'donePercent': _pct(current, contract),
        'totalPercent': '',
        'currentAmount': money(current),
        'totalAmount': '',
        'currentRetention': '',
        'totalRetention': '',
        'currentIssued': '',
        'totalIssued': '',
    }


def build_context(estimate):
    project = estimate.project_id
    categories = estimate.line_ids.filtered('is_summary_item')
    contract_amount = estimate.contract_amount or 0
    return {
        'project.name': project.name or '',
        'project.code': project.code or '',
        'project.constructionNo': estimate.contract_no or project.contract_no or '',
        'location': project.location or project.location_detail or '',
        'beginAt': roc_date(project.contract_start_date),
        'contractDuration': ('日曆天%s天' % project.contract_duration
                             if project.contract_duration else ''),
        'estimateDate': roc_date(estimate.estimate_date),
        'estimateNo': estimate.estimate_no or '',
        'paymentNo': estimate.estimate_no or '',
        'retentionRate': DEFAULT_RETENTION_RATE,
        'currentPage': 1,
        'totalPage': 1,
        'budgetAmount': money(project.budget_amount),
        'contractAmount': money(contract_amount),
        'changeNet': money(project.total_change_amount),
        'contractorName': contractor_name(project),

        # 合計列
        'totalContractAmount': money(contract_amount),
        'totalCurrentAmount': money(estimate.subtotal),
        'totalCumulativeAmount': '',
        'totalIssuedAmount': '',

        'categories': [_category(line, estimate.line_ids) for line in categories],
    }


def FILENAME(estimate):
    return '工程估驗計價單_%s_第%s次.xlsx' % (
        estimate.project_id.name or '', estimate.estimate_no or estimate.id)
