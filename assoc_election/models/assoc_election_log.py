from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import canonical_json, chain_hash, sha256_hex

LOG_ACTIONS = [
    ('state_change', '狀態變更'),
    ('reissue', '作廢重發'),
    # 封箱：關票之後、開票之前，把當下的票匭摘要釘進鏈。
    # 它**不是**狀態變更（狀態仍是 closed），所以不進 `_verify_chain` 的
    # transitions 比對，也不受「每個狀態只能出現一次」管——重複封箱由
    # `action_seal_ballots` 的守衛擋，離線則由 `ballots_sealed_matches` 判 FAIL。
    ('ballots_sealed', '封存票匭'),
    # 作廢封箱：封箱之後票匭與封存當下不符時，這場選舉原本沒有任何出口
    # （不能開票、不能重封、`action_cancel` 不吃 closed、也刪不掉），
    # 唯一的復原手段是下 SQL——而那是完全無痕的。所以留一條出口，但它入鏈。
    # 「現行是哪一筆封箱」由 `verify_core.live_seal()` 用排除法決定，
    # **不是**取最後一筆（那正是第四輪那個「往鏈尾追加就換掉基準」的洞）。
    ('ballots_seal_voided', '作廢封箱'),
]


class AssocElectionLog(models.Model):
    """選務稽核鏈：append-only，每筆以 prev_hash 串接。

    只記選務事件（狀態變更、作廢重發），不記逐人的領票與投票，避免重建投票時間軸。
    """
    _name = 'assoc.election.log'
    _description = '選務稽核鏈'
    _order = 'election_id, seq'

    election_id = fields.Many2one('assoc.election', string='選舉', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='election_id.company_id', store=True, index=True)
    seq = fields.Integer(string='序號', required=True, readonly=True)
    ts = fields.Char(string='時間 (UTC)', required=True, readonly=True)
    actor_uid = fields.Integer(string='操作者 ID', required=True, readonly=True)
    actor_name = fields.Char(string='操作者', readonly=True)
    action = fields.Selection(LOG_ACTIONS, string='事件', required=True, readonly=True)
    payload = fields.Json(string='內容（JSON）', readonly=True)
    payload_text = fields.Char(string='內容', compute='_compute_payload_text')
    prev_hash = fields.Char(string='前一筆雜湊', required=True, readonly=True)
    entry_hash = fields.Char(string='本筆雜湊', required=True, readonly=True)
    is_head = fields.Boolean(string='鏈頭', readonly=True)

    _sql_constraints = [
        ('election_seq_uniq', 'unique(election_id, seq)', '稽核鏈序號重複'),
    ]

    def init(self):
        # 每場選舉只能有一個鏈頭。兩筆「第一筆紀錄」同時寫入時，後者撞此索引而失敗，鏈不會分叉。
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS assoc_election_log_single_head
                ON assoc_election_log (election_id) WHERE is_head
        """)

    @api.depends('payload')
    def _compute_payload_text(self):
        for log in self:
            log.payload_text = canonical_json(log.payload) if log.payload is not None else ''

    def write(self, vals):
        raise UserError(_('稽核鏈不可修改'))

    def unlink(self):
        raise UserError(_('稽核鏈不可刪除'))

    @api.model
    def _append(self, election, action, payload=None):
        """在鏈尾追加一筆。

        併發序列化：先 UPDATE 目前鏈頭（is_head → false）。若另一交易已先改過同一列並 commit，
        PostgreSQL 在 REPEATABLE READ 下丟真正的 40001，Odoo 的 retrying 會用新快照重跑整個請求。
        （不能自己 raise SerializationFailure：沒有 pgcode，retrying 記 log 時會出錯。）
        """
        payload = payload or {}
        cr = self.env.cr
        self.env.flush_all()
        cr.execute("""
            UPDATE assoc_election_log SET is_head = false
             WHERE election_id = %s AND is_head
         RETURNING seq, entry_hash
        """, [election.id])
        head = cr.fetchone()
        seq, prev = (head[0] + 1, head[1]) if head else (1, sha256_hex(election.uuid))
        ts = cr.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        actor_uid = self.env.uid
        self.invalidate_model(['is_head'])
        return self.sudo().create({
            'election_id': election.id,
            'seq': seq,
            'ts': ts,
            'actor_uid': actor_uid,
            'actor_name': self.env.user.name,
            'action': action,
            'payload': payload,
            'prev_hash': prev,
            'entry_hash': chain_hash(election.uuid, seq, ts, actor_uid, action, payload, prev),
            'is_head': True,
        })
