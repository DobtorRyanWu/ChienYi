"""禮品權利名單與領取（計畫 §2.4、§9）。

一列＝「某位會員在某個品項上有一份」。領取走**單一條件 UPDATE**：
`state='pending'` 與唯一索引一起擋重領，兩台報到台同時按只有一台會拿到那一列，
另一台回報 `already` 而不是錯誤（現場不能讓人以為系統壞了）。

`state` 與所有領取欄位的寫入都要哨兵（P23）：報到台對本模型有寫入 ACL，
少了這道，帶 `assoc_gift=true` 的 RPC 就能把任何人的權利標成已領。
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.assoc_base.tools import GUARD, check_created, guarded

from .assoc_gift import ATTENDED_STATES, GUARD_GIFT, PICKUP

# 領取的管道：掃碼本人、掃碼代領、手動、造冊匯出
CHANNELS = [
    ('scan_self', '掃碼（本人）'),
    ('scan_proxy', '掃碼（代領）'),
    ('manual', '手動'),
    ('list', '造冊發放'),
]


class AssocGiftEntitlement(models.Model):
    _name = 'assoc.gift.entitlement'
    _description = '禮品權利'
    _order = 'campaign_id desc, member_no, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    campaign_id = fields.Many2one(
        'assoc.gift.campaign', string='活動', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one(
        'assoc.gift.item', string='品項', required=True, ondelete='cascade', index=True)
    member_id = fields.Many2one(
        'assoc.member', check_company=True, string='會員', required=True, ondelete='restrict', index=True)
    # related store：create 時不要傳值
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    member_no = fields.Char(related='member_id.member_no', store=True)
    member_name = fields.Char(related='member_id.name')
    delivery = fields.Selection(related='item_id.delivery', store=True)
    state = fields.Selection([
        ('pending', '未領取'), ('claimed', '已領取'),
        ('exported', '已造冊'), ('cancelled', '已取消'),
    ], string='狀態', default='pending', required=True, readonly=True, index=True)
    claimed_at = fields.Datetime(string='領取時間', readonly=True)
    claimed_by_uid = fields.Many2one('res.users', string='經手人', readonly=True)
    claim_channel = fields.Selection(CHANNELS, string='領取管道', readonly=True)
    holder_member_id = fields.Many2one(
        'assoc.member', check_company=True, string='代領人', readonly=True, ondelete='restrict')
    manual_reason = fields.Char(string='手動領取原因', readonly=True)
    export_id = fields.Many2one(
        'assoc.gift.export', string='造冊批次', readonly=True, ondelete='restrict', index=True)

    _sql_constraints = [
        ('item_member_uniq', 'unique(item_id, member_id)', '同一品項每位會員只有一份'),
    ]

    # ------------------------------------------------------------------
    # 守衛：白名單——建立之後**任何欄位**的寫入都要哨兵
    # ------------------------------------------------------------------
    def write(self, vals):
        if not guarded(self.env, GUARD_GIFT):
            raise AccessError(_('禮品領取狀態只能由領取或造冊動作變更。'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 驗結果不驗輸入：帶 `default_state='claimed'` 的 context 就能建出
        # 「已領取」的列，現場那份就被吃掉了
        check_created(records, {
            'state': 'pending', 'claimed_at': False, 'claimed_by_uid': False,
            'claim_channel': False, 'holder_member_id': False, 'export_id': False,
        }, GUARD_GIFT)
        return records

    def unlink(self):
        if not guarded(self.env, GUARD_GIFT):
            raise AccessError(_('禮品名單只能由「重建名單」刪除。'))
        if any(row.state != 'pending' for row in self):
            raise UserError(_('已經領取或造冊的權利不能刪除。'))
        return super().unlink()

    # ------------------------------------------------------------------
    # 領取
    # ------------------------------------------------------------------
    @api.model
    def _claimable_for(self, campaign, holder):
        """報到台掃到 `holder` 之後，他現在可以領的所有現場品項。

        包含本人的，以及他**有效禮品委託**的委託人的。
        回傳的順序固定（品項排序、會員編號），現場兩台機器看到的畫面一致。
        """
        principals = campaign._gift_principals_for(holder)
        rows = self.sudo().search([
            ('campaign_id', '=', campaign.id),
            ('state', '=', 'pending'),
            ('delivery', '=', PICKUP),
            ('member_id', 'in', (holder | principals).ids),
        ])
        attended = campaign._attended_member_ids() if campaign._needs_attendance() else None
        result = []
        for row in rows:
            blocked = attended is not None and row.member_id.id not in attended
            reason = ''
            if blocked:
                # 「尚未報到」對代領的情境會誤導：實際是**委託人**沒到，
                # 而這個活動的禮品是發給出席者的
                reason = (_('委託人尚未報到（本活動發給出席者）')
                          if row.member_id != holder else _('尚未報到'))
            result.append({
                'id': row.id,
                'item_name': row.item_id.name,
                'member_id': row.member_id.id,
                'member_no': row.member_id.member_no,
                'member_name': row.member_id.name,
                'is_self': row.member_id == holder,
                # 未出席的**照樣列出來**並標示原因：現場最怕的是「畫面上沒有」，
                # 承辦會以為系統壞了而改用手動，手動就沒有出席把關了
                'blocked': blocked,
                'blocked_reason': reason,
            })
        return result

    def _claim(self, campaign, holder, scanned, manual_reason=None):
        """把這些權利標成已領取。

        單一條件 UPDATE：`state='pending'` 擋重領、`delivery='pickup'` 擋造冊品項、
        出席條件（若適用）與「本人或有效委託」都寫在 WHERE 裡，
        兩台同時按只有一台會拿到那一列。回傳每一列的結果，沒拿到的逐列回報。

        `scanned` 決定管道：掃過碼的話本人與代領要分得開（對帳時「代領了幾份」
        是個要看的數字），所以用 CASE 在同一句裡決定，不拆成兩句 UPDATE。
        """
        if not self:
            return {}
        if campaign.state != 'open':
            raise UserError(_('這個禮品活動還沒開放領取。'))
        principals = campaign._gift_principals_for(holder)
        self.env.flush_all()
        # 代領時先**觸碰**委託列：只讀 EXISTS 在 RR 下會 write skew
        # （另一支交易同時取消委託，兩邊都覺得自己對）。
        # 真的 UPDATE 才會讓併發的那一支收到 40001 由 retrying 重跑。
        if principals:
            self.env.cr.execute("""
                UPDATE assoc_meeting_proxy SET activated_at = activated_at
                 WHERE meeting_id = %s AND purpose = 'gift' AND state = 'active'
                   AND holder_member_id = %s AND principal_member_id = ANY(%s)
                 RETURNING principal_member_id
            """, [campaign.meeting_id.id, holder.id, principals.ids])
        self.env.cr.execute("""
            UPDATE assoc_gift_entitlement g
               SET state = 'claimed', claimed_at = (now() AT TIME ZONE 'UTC'),
                   claimed_by_uid = %(uid)s,
                   claim_channel = CASE WHEN g.member_id = %(holder)s
                                        THEN %(channel_self)s ELSE %(channel_proxy)s END,
                   holder_member_id = %(holder)s, manual_reason = %(reason)s
              FROM assoc_gift_item i
             WHERE g.id = ANY(%(ids)s) AND g.campaign_id = %(cid)s
               AND g.company_id = %(company)s AND g.state = 'pending'
               AND i.id = g.item_id AND i.delivery = 'pickup'
               AND (NOT %(need_attend)s OR EXISTS (
                     SELECT 1 FROM assoc_meeting_attendance a
                      WHERE a.meeting_id = %(mid)s AND a.member_id = g.member_id
                        AND a.state = ANY(%(att_states)s)))
               AND (g.member_id = %(holder)s OR EXISTS (
                     SELECT 1 FROM assoc_meeting_proxy p
                      WHERE p.meeting_id = %(mid)s AND p.purpose = 'gift'
                        AND p.state = 'active' AND p.principal_member_id = g.member_id
                        AND p.holder_member_id = %(holder)s))
             RETURNING g.id
        """, {
            'uid': self.env.uid, 'holder': holder.id,
            'channel_self': 'scan_self' if scanned else 'manual',
            'channel_proxy': 'scan_proxy' if scanned else 'manual',
            'reason': manual_reason or None, 'ids': self.ids, 'cid': campaign.id,
            'company': campaign.company_id.id,
            'need_attend': campaign._needs_attendance(),
            'mid': campaign.meeting_id.id or 0,
            'att_states': list(ATTENDED_STATES),
        })
        claimed = {row[0] for row in self.env.cr.fetchall()}
        self.invalidate_model(['state', 'claimed_at', 'claimed_by_uid', 'claim_channel',
                              'holder_member_id', 'manual_reason'])
        if not scanned and claimed:
            self.env['assoc.audit.log']._log(
                'gift_manual_claim', records=self.browse(sorted(claimed)).member_id,
                company=campaign.company_id,
                detail={'campaign_id': campaign.id, 'holder_member_id': holder.id,
                        'reason': manual_reason or '', 'count': len(claimed)})
        return {row.id: ('claimed' if row.id in claimed else self._refusal(row, campaign))
                for row in self}

    def _refusal(self, row, campaign):
        """UPDATE 沒拿到這一列時，說得出是為什麼——現場要能當場處理。"""
        fresh = row.sudo().read(['state'])[0]['state'] if row.exists() else 'cancelled'
        if fresh != 'pending':
            return 'already'
        if row.item_id.delivery != PICKUP:
            return 'not_pickup'
        if campaign._needs_attendance() and row.member_id.id not in campaign._attended_member_ids():
            return 'not_attended'
        return 'no_permission'
