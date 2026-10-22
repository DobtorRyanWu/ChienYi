from odoo import fields, models

from .assoc_election import OFFICES

INVALID_REASONS = [
    ('blank', '空白'),
    ('over_mark', '圈選超過上限'),
    ('unknown_member', '圈選名冊外人員'),
    ('malformed', '格式錯誤'),
]


class AssocElectionBallot(models.Model):
    """選票。

    匿名性的核心：沒有選舉人外鍵、沒有 create_uid／create_date（_log_access=False），
    任何群組都沒有 ACL（只有 sudo 的投票與開票流程碰得到），
    開票時整批 DELETE + 亂序 INSERT，讓 id 與 xmin 都不再對應投票順序。
    """
    _name = 'assoc.election.ballot'
    _description = '選票'
    _log_access = False
    _order = 'id'

    election_id = fields.Many2one('assoc.election', string='選舉', required=True, ondelete='restrict', index=True)
    office = fields.Selection(OFFICES, string='職位', required=True)
    # 去重、排序後的會員 id 陣列（空陣列＝空白票，所以不設 required）
    choices = fields.Json(string='圈選')
    status = fields.Selection([('valid', '有效'), ('invalid', '無效')], string='效力', required=True)
    invalid_reason = fields.Selection(INVALID_REASONS, string='無效原因')
