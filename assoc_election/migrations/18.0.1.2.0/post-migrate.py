"""18.0.1.2.0：新增屆次（`term_id`／`term_no`，選罷辦法 §6 要求選票載明屆次）。

**沒有資料要搬**：兩個欄位對既有選舉一律留空／0，而離線驗算對「鏈上沒有
`term_no`」判不適用（N/A），所以舊的封存包照樣驗得過。

**升級指令要帶 `assoc_base`。** `assoc_election/views/assoc_term_views.xml`
繼承 `assoc_base.assoc_term_view_form`，而 `assoc_base` 這一版才新增那個 view。
只跑 `-u assoc_election` 會找不到 external id 而中止升級。

這支的工作是**升級後自己回頭確認兩件事**：
①**已經凍結名冊的場次缺不缺這次新增的 §6 要件**——升級當下已凍結名冊的選舉
拿不到屆次，而 `term_no` 只有 `action_ready` 寫得了、它又只吃 `draft`，所以只能
在升級時就讓人知道（抗辯指出）。**還沒開始投票的（`ballot_ready`）有補救路徑**：
取消、重建、重新凍結（`EDITABLE_STATES` 放行取消，同一場大會可以有第二場選舉）；
原本這裡寫「沒有補救路徑」，警告也只叫人書面補充，漏了這一條（第五輪 skeptic）。
②既有已凍結的選舉鏈還驗得過（計畫列為 M11–M13 的第一項驗收）。

**原本還有第三項「職位集合沒被動到」，已刪**：那一項是為「加席次欄位的那一版」
寫的，而這一版沒有加任何席次欄位，自己的 docstring 也承認它「只是便宜的保險」
（第二輪 simplifier）。M13 第二階段的 OFFICES 擴充落地時，要在**那一版**的
migration 寫它。

**migration 只在版號跨越時跑一次，不是每次升級都跑**（之後同版號的
`-u assoc_election` 不會再進來）。所以它買到的是「每個庫各查一次」
——dev／範本／各租戶各一次，而不是一道常駐的網。

**刻意只警告、不中止升級**：資料庫裡本來就可能有鏈真的壞掉的紀錄（測試殘料、
歷史事故），為了它們擋住整個升級會讓人改去用別的方式繞過，那比看不到警告更糟。
真的要看的是 log 裡這幾行。
**所以複查本身必須包在 try 裡**：`_verify_chain()` 讀 `log.payload.get('to')`，
payload 被改成非 dict 的紀錄會讓它丟 AttributeError（它只先接住「雜湊不符」
那一種失敗），一筆就足以讓整個模組升級 rollback——那正是這段 docstring 說
不可以發生的事（第二輪 red-team）。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# 「升級之後選票上少了 §6 要件」的受害者＝**升級前就已經凍結名冊、而且沒有屆次**
# 的每一場，不是只有「還在發票」的那幾場。原本只列 ballot_ready/open/closing，
# 於是 `closed` 與 `counted` 的場次從頭到尾不會被點名——而它們的票**早就發出去了**
# （而且還會被公告），受害程度與 open 的一模一樣。實查 `assoc_compat_m13`：
# `closed` 且沒有屆次的有 2 場（另有 open 12 場、draft 2 場）。
# 判準寫成「還在發票」是看錯了時點：要件缺在**票面**上，而票面在凍結那一步就定了
# （第四輪 skeptic；L1⑫「承諾的時點」的同一條）。
# `published` 不列：那一屆已經選完公告了，書面補充說明的對象是還沒結束的那幾場。
IN_FLIGHT_STATES = ('ballot_ready', 'open', 'closing', 'closed', 'counted')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Election = env['assoc.election']
    # **第①項先查、警告印在最後一個**：它是這次改動真正的後果，查詢本身不碰
    # 任何可能爆的東西，而 log 的最後一行最容易被執行升級的人看到。
    # `('term_no', '=', 0)` 也收得到升級剛加上欄位、值還是 NULL 的列——Odoo 18
    # 對數值欄位的 `= 0` 會展開成 `(term_no = 0 OR term_no IS NULL)`
    # （容器內 `odoo/models.py:3273-3279`，第二輪 skeptic 與 red-team 各自實查）。
    in_flight = Election.search([('state', 'in', IN_FLIGHT_STATES), ('term_no', '=', 0)])
    frozen = Election.search([('state', 'not in', ('draft', 'cancelled'))])
    broken_chain = []
    crashed = []
    for election in frozen:
        # 一筆壞掉的 payload 不可以讓整個升級 rollback（見檔頭）。
        # 這裡也**不要把「驗不過」與「驗不動」混成同一個數字**：前者是鏈的
        # 內容對不上，後者是紀錄壞到連驗算都跑不完，處置方式不一樣。
        try:
            if not election._verify_chain():
                broken_chain.append(election.id)
        except Exception as error:               # noqa: BLE001 — 升級不可以因此中止
            crashed.append((election.id, type(error).__name__))
    _logger.info('屆次升級後複查：%s 場已凍結的選舉，稽核鏈不過 %s 場、驗不動 %s 場、'
                 '已凍結名冊但沒有屆次 %s 場',
                 len(frozen), len(broken_chain), len(crashed), len(in_flight))
    if broken_chain:
        # **不要只印筆數**：筆數說不出要去看哪一場，而這份 log 是唯一的線索。
        _logger.warning('下列選舉的稽核鏈驗不過（升級前就已如此，本次升級不會改變鏈的內容）：%s',
                        broken_chain)
    if crashed:
        _logger.warning('下列選舉連驗鏈都跑不完（紀錄本身壞掉，例如 payload 不是物件）：%s',
                        crashed)
    if in_flight:
        # **要點出是哪幾場可以補救**：補救路徑只對還沒開始投票的成立，而只印 id
        # 的話，看 log 的人分不出哪幾場是（第六輪 simplifier）。最後一個參數維持
        # 「全部受影響的 id」，測試從它取點名集合。
        not_started = in_flight.filtered(lambda election: election.state == 'ballot_ready')
        _logger.warning(
            '下列選舉在升級當下已經凍結名冊（含正在投票、已關票、已開票），'
            '**選票上不會有選舉屆次**'
            '（選罷辦法 §6 的載明事項）——屆次快照只在凍結名冊那一步寫得進去。'
            '其中還沒開始投票的（狀態「名冊已凍結」）可以取消後重建、重新凍結：%s；'
            '其餘請改以書面補充說明，或在本屆結束前不要升級。全部受影響的場次：%s',
            not_started.ids, in_flight.ids)
