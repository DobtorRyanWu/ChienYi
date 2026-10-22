from odoo import fields, models


class AssocElection(models.Model):
    _inherit = 'assoc.election'

    registration_deadline = fields.Datetime(
        string='候選人登記截止',
        # **copy=False 是必要的**：「複製上屆選舉」是最自然的建檔方式，而帶著舊的
        # （已過期的）截止日複製出來的那筆草稿，在前台的可見性判斷上就不是草稿了
        # ——不需要任何人犯錯就會提前曝光。
        copy=False,
        help='填了才開放前台自助登記；空白＝只能由承辦後台建檔。')

    # 這個欄位**刻意不加進 `SYSTEM_FIELDS`**：它不是開票結果、也不是狀態機的一部分。
    # 既有的 write 安全帶（`assoc_election.py:213`）本來就會在 `draft` 之後擋掉
    # 所有非白名單的業務欄位寫入，所以「名冊凍結後不能偷偷延長登記期」是白送的，
    # 不必再寫一條守衛。改這一行之前先確認那道安全帶還在。
