"""會員自助登記參選／退選。

**所有閘門都在這一層，controller 只負責解出「登入者是哪一位會員」。**
理由與 `assoc_portal` 其他前台功能相同：share 使用者對 `assoc.*` 沒有任何 ACL，
路由一律 sudo，所以「這個人可不可以做這件事」如果寫在 controller，
日後多一條路由就會漏掉一次（L4：先列出能達成同一效果的所有路徑）。
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.assoc_election.models.assoc_election import OFFICES

# 自助登記只動得了自己這一筆，而且只在「已登記」這個狀態
# （承辦按過「確認」之後名單可能已經對外公布，退選要走後台留軌跡）
SELF_WITHDRAWABLE_STATES = ('registered',)


class AssocElectionCandidate(models.Model):
    _inherit = 'assoc.election.candidate'

    @api.model
    def _registration_open(self, election):
        """這場現在收不收自助登記。前台列表與兩個動作共用同一個判斷。"""
        return bool(
            election.registration_deadline
            and election.state == 'draft'
            and fields.Datetime.now() <= election.registration_deadline
        )

    @api.model
    def _register_self(self, election, member, office):
        """會員本人登記參選。回傳新建的候選人列。

        **刻意不帶哨兵 context**：既有的 `_check_editable`（限 `draft`）與
        `check_created`（`state` 必須是 `registered`、快照與票數必須是空的）
        正好就是這條路要的限制，走一般 create 讓它們全部生效。
        帶哨兵反而會把那兩道關掉——哨兵是給流程用的鑰匙，不是給前台用的。
        """
        election.ensure_one()
        member.ensure_one()
        if not election.registration_deadline:
            raise UserError(_('這場選舉沒有開放線上登記，請洽公會辦公室。'))
        if election.state != 'draft':
            raise UserError(_('候選人名冊已經凍結，不能再登記。'))
        if fields.Datetime.now() > election.registration_deadline:
            raise UserError(_('候選人登記已經截止。'))
        if office not in dict(OFFICES):
            raise UserError(_('職位不正確。'))
        if member.company_id != election.company_id:
            # 不說「這是別家公會的選舉」——那會變成跨公會的存在性探測器
            raise UserError(_('查不到這場選舉。'))
        if not member.is_voter_eligible:
            raise UserError(_('會籍或會費狀態不符合參選資格，請洽公會辦公室。'))
        if office not in election._active_offices():
            # `_active_offices()` 就是「席次 > 0 的職位」，與選票頁用的是同一支
            raise UserError(_('這場選舉沒有要選這個職位。'))
        existing = self.sudo().search([
            ('election_id', '=', election.id),
            ('office', '=', office),
            ('member_id', '=', member.id),
        ], limit=1)
        if existing:
            # 退選過的要由承辦處理：是否准許重新登記是人的判斷，不是程式的
            raise UserError(_('你已經登記過這個職位了。'))
        candidate = self.sudo().create({
            'election_id': election.id,
            'office': office,
            'member_id': member.id,
        })
        self.env['assoc.audit.log']._log(
            'candidate_self_register', records=member, company=election.company_id,
            detail={'election_id': election.id, 'office': office,
                    'candidate_id': candidate.id})
        return candidate

    def _withdraw_self(self, member):
        """會員本人退選。只動得了自己那一筆、只在登記期內、只從「已登記」。"""
        self.ensure_one()
        candidate = self.sudo()
        if candidate.member_id != member:
            # 不區分「不存在」與「不是你的」
            raise UserError(_('查不到這筆登記。'))
        if not self._registration_open(candidate.election_id):
            raise UserError(_('登記期已經結束，退選請洽公會辦公室。'))
        if candidate.state not in SELF_WITHDRAWABLE_STATES:
            raise UserError(_('這筆登記已經由公會確認，退選請洽公會辦公室。'))
        candidate.write({'state': 'withdrawn'})
        self.env['assoc.audit.log']._log(
            'candidate_self_withdraw', records=member,
            company=candidate.election_id.company_id,
            detail={'election_id': candidate.election_id.id,
                    'office': candidate.office, 'candidate_id': candidate.id})
        return candidate
