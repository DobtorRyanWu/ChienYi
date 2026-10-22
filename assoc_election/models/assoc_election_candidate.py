from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.assoc_base.tools import check_created, guarded

from .assoc_election import GUARD_STATE, OFFICES

# 候選人只能在草稿階段調整（凍結名冊＝候選人登記完成）
CANDIDATE_EDITABLE_STATES = ('draft',)


class AssocElectionCandidate(models.Model):
    _name = 'assoc.election.candidate'
    _description = '候選人'
    _order = 'election_id, office, sequence, member_no, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    election_id = fields.Many2one('assoc.election', string='選舉', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='election_id.company_id', store=True, index=True)
    office = fields.Selection(OFFICES, string='職位', required=True, default='director')
    member_id = fields.Many2one('assoc.member', check_company=True, string='會員', required=True, ondelete='restrict',
                                domain="[('company_id', '=', company_id)]")
    # 凍結名冊時的快照（選票頁與開票結果讀這裡，不讀即時會員資料）
    member_no = fields.Char(string='會員編號', readonly=True)
    member_name = fields.Char(string='姓名', readonly=True)
    sequence = fields.Integer(string='排序', default=10)
    state = fields.Selection([
        ('registered', '已登記'),
        ('confirmed', '已確認'),
        ('withdrawn', '已退選'),
        ('write_in', '名單外得票'),
    ], string='狀態', default='registered', required=True)
    ballot_number = fields.Integer(
        string='號次',
        help='草稿時可手填（實體抽籤的結果）；填了「抽籤亂數」的話由系統在凍結名冊時決定。')
    votes = fields.Integer(string='得票數', readonly=True)
    rank = fields.Integer(string='名次', readonly=True)
    result = fields.Selection([
        ('elected', '當選'),
        ('alternate', '候補'),
        ('none', '未當選'),
    ], string='結果', readonly=True)

    _sql_constraints = [
        ('election_office_member_uniq', 'unique(election_id, office, member_id)', '同一職位不可重複登記同一位會員'),
    ]

    @api.constrains('member_id', 'election_id')
    def _check_member_company(self):
        for cand in self:
            if cand.member_id.company_id != cand.election_id.company_id:
                raise ValidationError(_('候選人必須是本公會會員'))

    def _check_editable(self, elections):
        if guarded(self.env, GUARD_STATE):
            return
        if any(e.state not in CANDIDATE_EDITABLE_STATES for e in elections):
            raise UserError(_('名冊已凍結，候選人不可再變更'))

    def _check_system_values(self, vals_list):
        # 「名單外得票」與快照欄位只由選務流程寫入；手動設成名單外得票會繞過凍結名冊的選舉權檢查
        if guarded(self.env, GUARD_STATE):
            return
        for vals in vals_list:
            if vals.get('state') == 'write_in' or {'member_no', 'member_name', 'votes', 'rank', 'result'} & set(vals):
                raise UserError(_('名單外得票、快照與開票結果由系統產生，不可手動設定'))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_system_values(vals_list)
        self._check_editable(self.env['assoc.election'].browse(
            {vals['election_id'] for vals in vals_list if vals.get('election_id')}))
        records = super().create(vals_list)
        # 只看 vals 擋不住 `default_*` 與使用者自建的 `ir.default`（§16 通則 1）：
        # `default_state='write_in'` 會建出「名單外得票」，繞過凍結名冊的選舉權檢查；
        # `default_votes` 則是直接捏造票數。
        check_created(records, {
            'state': 'registered', 'member_no': False, 'member_name': False,
            'votes': 0, 'rank': 0, 'result': False,
        }, GUARD_STATE)
        # `ballot_number` 刻意不列：草稿階段本來就可以手填（實體抽籤的結果）
        return records

    def write(self, vals):
        self._check_system_values([vals])
        targets = self.election_id
        if vals.get('election_id'):
            targets |= self.env['assoc.election'].browse(vals['election_id'])
        self._check_editable(targets)
        return super().write(vals)

    def unlink(self):
        self._check_editable(self.election_id)
        return super().unlink()
