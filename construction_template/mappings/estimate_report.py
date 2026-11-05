# -*- coding: utf-8 -*-
"""工程估驗計價單 —— 佔位符對照表。

樣板原本內嵌來源專案的值（日曆天270天／臺北市／工務科北區工務所／
第1次估驗，第1次付款）與 3 個未引用的殘留字串（真實契約編號與金額），
2026-08-05 重做成佔位符 + 一列 `${table:categories.*}` 明細樣板列。

明細區印的是**最上層大類**（工項樹的根，實際每張 7~11 個），
原本的 7 列固定列不夠用，所以改成動態展開。

## 分類＝葉節點依工項樹的最上層祖先分組（2026-11-05）

原本是「所有彙總列各一列，子項用 item_no + '.' 前綴找」——三個問題，真實資料都會中：
壹／一／(一)／1 這種每層重新編號的項次前綴永遠對不到 → 分類列 0（dev 380、388）；
大類與底下的子類混列、加總大於合計；匯入建的估驗單只有葉節點 → 分類區整段空白
（500 的 14 張、503 的 23 張）。使用者要「照原系統」：EAGLE 正式版沒有產這張表，
原始已填紙本（tools/gen_doc_templates/staging/raw/estimate_report.xlsx）只列最上層
（一列「發包工程費」、金額等於合計）。所以分類不依賴估驗單有沒有彙總列，直接看工項樹。

## 沒有資料來源的欄位（留白由人工填）

會計科目、承辦工務所、已工作日數、本期核發／應扣／實發金額、
以前核發金額、總計核發金額、各大類的保留金額與核發金額
——payment.estimate 沒有這些欄位，硬湊會產生假數字。
"""

from ..utils.formatters import contractor_name, money, roc_date
from .progress_report import _leaf_contract_amount

MODEL = 'payment.estimate'
MODE = 'placeholder'

# 保留款比率：全系統沒有這個欄位（只有 payment.claim.retention_amount 是金額）。
# 原樣板把 5% 寫死在儲存格裡，這裡改成具名常數——公共工程慣例是 5%，
# 但**契約不同就要改**，之後若模型補上欄位應改讀該欄位。
DEFAULT_RETENTION_RATE = 5


def _pct(part, whole):
    return '%.2f' % (part / whole * 100) if whole else ''


def _top_ancestor(task):
    """工項樹的最上層祖先（含自己）"""
    while task.parent_id:
        task = task.parent_id
    return task


def _top_categories(project):
    """{item_no: 最上層彙總工項}——孤兒工項依項次第一段找回大類用"""
    tops = project.env['project.task'].search([
        ('project_id', '=', project.id), ('parent_id', '=', False),
        ('is_summary_item', '=', True)])
    return {t.item_no: t for t in tops if t.item_no}


def _category_task(task, tops):
    """這個葉節點歸在哪一個最上層大類。

    🔴 孤兒修補：工項 parent 斷掉時（dev 500 有 97 個像「1.1.24」這樣 parent 為空的
    葉節點）它自己就是根，會各自變成一列。只在「根是葉節點、沒有 parent、項次帶點號、
    同工程有項次等於第一段的最上層彙總工項」時併回那一類——條件寫死，其他一律照工項樹。
    """
    root = _top_ancestor(task)
    item_no = root.item_no or ''
    if root == task and not root.is_summary_item and '.' in item_no:
        return tops.get(item_no.split('.')[0], root)
    return root


# 「前期已核定」的狀態，與 payment.estimate.line._compute_previous_approved_qty 相同
APPROVED_STATES = ('approved', 'archived')


def _earlier_approved(estimate):
    """排在本張前面、已核定的估驗單，由早到晚（與模型的「前期已核定累計」同一套定義：
    _estimates_before() 的順序＝畫面上「第N次」的順序；同一天好幾期也排得對）。

    沒有估驗日期時模型的前期一律算 0（estimate_warnings 會提醒使用者），這裡跟著一樣。
    """
    if not estimate.estimate_date:
        return estimate.browse()
    return estimate._estimates_before().filtered(lambda e: e.state in APPROVED_STATES)


def _leaves(estimate):
    return estimate.line_ids.filtered(lambda ln: not ln.is_summary_item).sorted(
        lambda ln: (ln.sequence, ln.id))


def _categories(estimate):
    """各大類的 {name, contract, current, cumulative}，依明細順序（＝契約順序）。

    最上層的單一工項（例如「營業稅」）自己就是一類。

    🔴 累計與契約金額要看「本張＋前面已核定各期」的明細，不能只看本張：匯入建的估驗單
    只列本期有填的工項（3.5.4），前期估過、本期沒列的工項只加本張的話就整筆消失
    （2026-11-05 審查實查：dev 500 第 30 期印出累計 2,274 萬，全部工項約 5.4 億；
    67 張裡 52 張各分類契約合計對不上）。
      本次＝本張葉節點的本次估驗金額（加總＝契約工項小計）
      累計＝本次＋前面各期已核定葉節點的金額（同模型 previous_approved_amount 的算法，
            _get_effective_amount：手動金額照手動值、單價照當期快照）
      契約＝出現過的每個工項取「最新一期」明細的契約快照（_leaf_contract_amount）
    ⚠️ 不要改成「大類工項的 planned_amount」：2026-11-05 試過，dev 匯入的工程工項樹是
    好幾套疊在一起的（380 有 79 個根：一個彙總樹＋「總計」「發包工程費」單筆＋平鋪工項），
    彙總項的 planned_amount 常是 0；「根工項合計＝工程契約金額」是因為工程契約金額本來
    就是那樣加出來的，不是證據。
    """
    tops = _top_categories(estimate.project_id)
    category_of = {}         # 工項 id → 大類（一張單上百列，往上走 parent 每個工項只做一次）
    rows = {}

    def row(task):
        if task.id not in category_of:
            category_of[task.id] = _category_task(task, tops)
        category = category_of[task.id]
        return rows.setdefault(category.id, {
            'name': category.name or '', 'snapshot': {}, 'current': 0.0, 'earlier': 0.0})

    for line in _leaves(estimate):
        entry = row(line.task_id)
        entry['current'] += line.estimate_amount or (line.estimate_qty * line.unit_price)
        entry['snapshot'][line.task_id.id] = line
    for earlier in _earlier_approved(estimate)[::-1]:       # 由晚到早：契約快照取最新一期
        for line in _leaves(earlier):
            entry = row(line.task_id)
            entry['earlier'] += line._get_effective_amount()
            entry['snapshot'].setdefault(line.task_id.id, line)
    return [{'name': entry['name'],
             'contract': sum(_leaf_contract_amount(ln) for ln in entry['snapshot'].values()),
             'current': entry['current'],
             'cumulative': entry['current'] + entry['earlier']}
            for entry in rows.values()]


def _category(category):
    """明細大類一列。保留金額與核發金額模型沒有對應欄位，留白由人工填。"""
    contract, current, cumulative = (
        category['contract'], category['current'], category['cumulative'])
    return {
        'name': category['name'],
        'contractAmount': money(contract),
        'donePercent': _pct(current, contract),
        'totalPercent': _pct(cumulative, contract),
        'currentAmount': money(current),
        'totalAmount': money(cumulative),
        'currentRetention': '',
        'totalRetention': '',
        'currentIssued': '',
        'totalIssued': '',
    }


def build_context(estimate):
    project = estimate.project_id
    categories = _categories(estimate)
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

        # 合計列（僅合約項）：本次用契約工項小計——subtotal 含有勾「計入估驗總額」的
        # 非契約工項（物價調整等），印在「僅合約項」這一列是錯的
        'totalContractAmount': money(contract_amount),
        'totalCurrentAmount': money(estimate.contract_subtotal),
        'totalCumulativeAmount': money(sum(c['cumulative'] for c in categories)),
        'totalIssuedAmount': '',

        'categories': [_category(category) for category in categories],
    }


def FILENAME(estimate):
    return '工程估驗計價單_%s_第%s次.xlsx' % (
        estimate.project_id.name or '', estimate.estimate_no or estimate.id)
