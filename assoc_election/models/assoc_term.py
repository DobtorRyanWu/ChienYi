"""屆次上與選舉有關的部分（模型本體在 `assoc_base`）。

分層理由：`assoc.term` 是公會層級的資料（理監事任期），不該知道選舉的存在；
但「這一屆有哪些選舉」與「被選舉凍結之後屆次就不能改」是選舉的規則，
所以放在這裡以 `_inherit` 補上。只裝 `assoc_base` 的環境不會載到這一段。
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class AssocTerm(models.Model):
    _inherit = 'assoc.term'

    election_ids = fields.One2many('assoc.election', 'term_id', string='本屆的選舉')

    def write(self, vals):
        if 'term_no' in vals or 'company_id' in vals:
            # 屆次一旦被某場選舉凍結（`ballot_ready` 的 payload、選舉上的
            # `term_no` 快照、以及印出去的選票），在這裡改就會讓後台顯示的數字
            # 與鏈上的、紙上的互相矛盾。鏈與快照本身改不動，所以這不是資料毀損
            # ——但監票員拿紙本選票來對的時候，沒有人說得出哪一個才算數。
            # **判準是 `term_no` 快照，不是選舉狀態。** 原本寫 `state != 'draft'`
            # 把 `cancelled` 也算進去：一場建了又取消、從來沒凍結過名冊、沒有鏈
            # 也沒有票的選舉，會永久鎖死這一屆，而錯誤訊息還宣稱「已經有選舉
            # 凍結名冊」——訊息與事實不符。同一批的 migration 用的又是
            # `state not in ('draft','cancelled')`，兩處定義不一致。
            # 快照只有 `action_ready` 寫得出來，它存在就代表真的凍結過。
            # **併發**：這是 Python 層的判斷，而凍結名冊寫的是選舉那一列——兩者可以
            # 同時成立，於是後台第 13 屆、鏈上與票上第 12 屆（write skew，第三輪 red-team）。
            # 擋它的是兩邊都**寫**屆次這一列（這裡的 UPDATE、`action_ready` 的 no-op
            # UPDATE），REPEATABLE READ 下後到的吃 40001、整個請求重跑；理由與兩種先後
            # 順序的實證在 `test_term_concurrency.py`。這裡不另外鎖（第四輪那句 `FOR UPDATE`
            # 在第六輪拿掉：只鎖不改不會重讀，它只讓 40001 早幾行出現）。
            locked = self.filtered(
                lambda term: any(e.term_no for e in term.election_ids))
            if locked:
                raise UserError(_(
                    '「%(name)s」已經有選舉凍結名冊，屆次與所屬公會不可以再改。',
                    name='、'.join(locked.mapped('display_name'))))
        return super().write(vals)
