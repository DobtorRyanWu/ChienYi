"""禮品活動與品項（計畫 §2.4、§9）。

一場禮品活動（例如「第 12 屆會員大會紀念品」）底下有數個品項；
按下「產生名單」時，依**當下**的資格口徑為每個品項 × 每位合格會員建一列權利
（`assoc.gift.entitlement`）。資格是**快照**：名單一旦產生就不隨會員狀態浮動，
否則同一個人早上領得到、下午領不到，現場無法處理。

唯一的例外是「大會出席者」這個口徑：名單以大會名冊建列，
**出席與否在領取當下才檢查**——名單產生時大會根本還沒開始報到。
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.assoc_base.tools import GUARD, check_guild_admin, with_guard

GUARD_GIFT = 'assoc_gift'

# 委託出席算不算「出席」(H)：預設**不算**——代理人不是本人到場，
# 而禮品多半是給到場的人。公會確認後改這個常數（§14 #9）。
PROXY_COUNTS_AS_ATTENDANCE = False
ATTENDED_STATES = ('present',) + (('proxy',) if PROXY_COUNTS_AS_ATTENDANCE else ())

# 名單產生之後就不能再改的定義欄位：改了會讓已經發出去的權利列對不上快照
CAMPAIGN_LOCKED_ONCE_ISSUED = frozenset({'eligibility', 'meeting_id', 'company_id'})

PICKUP = 'pickup'


class AssocGiftCampaign(models.Model):
    _name = 'assoc.gift.campaign'
    _description = '禮品活動'
    _order = 'id desc'

    name = fields.Char(string='活動名稱', required=True)
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, index=True,
        default=lambda self: self.env.company)
    meeting_id = fields.Many2one(
        'assoc.meeting', string='對應大會', index=True, ondelete='restrict',
        help='現場領取的品項必須綁一場大會（領取要在報到台掃碼）。')
    # ondelete='restrict'：預設的 `set null` 會讓刪大會變成「看起來成功」的破壞——
    # 活動的 `meeting_id` 被清空、所有領取永遠回 not_attended，
    # 而 `meeting_id` 已被 `CAMPAIGN_LOCKED_ONCE_ISSUED` 鎖住，改不回去。
    eligibility = fields.Selection([
        ('attendees', '大會出席者'),
        ('active_members', '有效會員'),
        ('fee_current', '會費有效的會員'),
    ], string='發放對象', required=True, default='attendees')
    state = fields.Selection([
        ('draft', '草稿'), ('ready', '名單已產生'), ('open', '開放領取'), ('closed', '已結束'),
    ], string='狀態', default='draft', required=True, readonly=True)
    snapshot_at = fields.Datetime(string='名單產生時間', readonly=True)
    item_ids = fields.One2many('assoc.gift.item', 'campaign_id', string='品項')
    entitlement_ids = fields.One2many(
        'assoc.gift.entitlement', 'campaign_id', string='權利名單')
    entitlement_count = fields.Integer(string='名單筆數', compute='_compute_stats')
    claimed_count = fields.Integer(string='已領取', compute='_compute_stats')
    pending_count = fields.Integer(string='未領取', compute='_compute_stats')

    _sql_constraints = [
        ('name_uniq', 'unique(company_id, name)', '同一公會的禮品活動名稱不可重複'),
    ]

    @api.depends('entitlement_ids.state')
    def _compute_stats(self):
        for campaign in self:
            rows = campaign.entitlement_ids
            campaign.entitlement_count = len(rows)
            campaign.claimed_count = len(rows.filtered(
                lambda e: e.state in ('claimed', 'exported')))
            campaign.pending_count = len(rows.filtered(lambda e: e.state == 'pending'))

    @api.constrains('meeting_id', 'company_id')
    def _check_meeting(self):
        for campaign in self:
            meeting = campaign.meeting_id
            if not meeting:
                continue
            if meeting.company_id != campaign.company_id:
                raise UserError(_('大會與禮品活動必須屬於同一公會。'))
            if meeting.kind != 'assembly':
                raise UserError(_('禮品活動只能綁會員大會，不能綁研討會。'))

    def write(self, vals):
        locked = CAMPAIGN_LOCKED_ONCE_ISSUED & set(vals)
        # 判準是「**名單產生了沒**」而不是狀態：名單是快照，改了發放對象
        # 或綁定的大會，已經發出去的權利列就對不上它宣稱的口徑。
        # 名單還沒產生前隨便改（打錯了就改回來），產生後要改請刪名單重來。
        if locked and any(campaign.entitlement_ids for campaign in self):
            raise AccessError(_('「%s」在名單產生之後不能再改；要改請先刪掉名單。',
                                '、'.join(sorted(locked))))
        return super().write(vals)

    def unlink(self):
        """有人領過就不准刪活動。

        `assoc.gift.entitlement.campaign_id` 是 `ondelete='cascade'`，而 Odoo 的
        `unlink()` 是直接 `DELETE FROM`——**子模型的 `unlink()` 永遠不會被呼叫**，
        權利列自己那句「已經領取或造冊的權利不能刪除」在這條路上等於不存在。
        不擋的話：刪活動 → 重建名單 → 同一份再領一次，而且第一次的領取軌跡
        （誰、何時、哪台）一起消失。
        """
        used = self.entitlement_ids.filtered(lambda row: row.state != 'pending')
        if used:
            raise UserError(_('已經有 %s 筆領取或造冊紀錄，活動不能刪除；'
                              '要停止發放請按「結束活動」。', len(used)))
        return super().unlink()

    # ------------------------------------------------------------------
    def _check_admin(self):
        check_guild_admin(self, _('只有公會管理員可以維護禮品活動。'))

    def _eligible_members(self):
        """依口徑取出這次要建名單的會員。

        `attendees` 用大會**名冊**（出席紀錄）而不是「已報到的人」：
        名單要在報到開始前就印得出來，出席與否在領取當下才檢查。
        """
        self.ensure_one()
        Member = self.env['assoc.member']
        if self.eligibility == 'attendees':
            if not self.meeting_id:
                raise UserError(_('發放對象是「大會出席者」時必須指定大會。'))
            return self.meeting_id.attendance_ids.member_id
        members = Member.search([('company_id', '=', self.company_id.id)])
        if self.eligibility == 'fee_current':
            return members.filtered(lambda m: m._fee_is_current())
        return members

    def action_ready(self):
        """產生名單快照：每個品項 × 每位合格會員一列。

        可重複執行（只補缺的）：現場常常臨時加一個品項，
        重按一次就好，已經領走的列不會被動到（unique 擋住重建）。
        """
        self.ensure_one()
        self._check_admin()
        if self.state == 'closed':
            raise UserError(_('已結束的活動不能再產生名單。'))
        if not self.item_ids:
            raise UserError(_('請先建立至少一個品項。'))
        if any(item.delivery == PICKUP for item in self.item_ids) and not self.meeting_id:
            raise UserError(_('有「現場領取」的品項時必須指定大會。'))
        members = self._eligible_members()
        if not members:
            # 無聲成功是最糟的：狀態變成 ready、承辦以為名單好了，
            # 到了現場才發現一個人都沒有（「驗收閘必須分得出通過與沒跑」）
            raise UserError(_('沒有符合「%s」的會員，名單是空的。',
                              dict(self._fields['eligibility'].selection)[self.eligibility]))
        existing = {(row.item_id.id, row.member_id.id) for row in self.entitlement_ids}
        values = [{
            'campaign_id': self.id, 'item_id': item.id, 'member_id': member.id,
        } for item in self.item_ids for member in members
            if (item.id, member.id) not in existing]
        with_guard(self.env['assoc.gift.entitlement'], GUARD_GIFT).create(values)
        self.write({
            'state': 'open' if self.state == 'open' else 'ready',
            'snapshot_at': fields.Datetime.now(),
        })
        return len(values)

    def action_open(self):
        self.ensure_one()
        self._check_admin()
        if self.state != 'ready':
            raise UserError(_('只有「名單已產生」的活動可以開放領取。'))
        self.state = 'open'
        return True

    def action_close(self):
        self.ensure_one()
        self._check_admin()
        if self.state not in ('ready', 'open'):
            raise UserError(_('只有進行中的活動可以結束。'))
        self.state = 'closed'
        return True

    def action_reset_list(self):
        """刪掉名單重來（只有還沒有人領走時才允許）。"""
        self.ensure_one()
        self._check_admin()
        claimed = self.entitlement_ids.filtered(lambda e: e.state != 'pending')
        if claimed:
            raise UserError(_('已經有 %s 筆領取或匯出的紀錄，名單不能重建。', len(claimed)))
        self.entitlement_ids.with_context(**{GUARD_GIFT: GUARD}).unlink()
        self.write({'state': 'draft', 'snapshot_at': False})
        return True

    def _needs_attendance(self):
        """領取當下要不要檢查出席。"""
        self.ensure_one()
        return self.eligibility == 'attendees'

    def _attended_member_ids(self):
        """這場大會目前算「出席」的會員 id。

        委託出席算不算由 `PROXY_COUNTS_AS_ATTENDANCE` 決定，
        而且**報到台與 SQL 用的是同一個常數**——兩邊各寫一份遲早會漂移。
        """
        self.ensure_one()
        if not self.meeting_id:
            return set()
        return set(self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', self.meeting_id.id),
            ('state', 'in', list(ATTENDED_STATES)),
        ]).member_id.ids)

    def _gift_principals_for(self, holder):
        """這位受託人可以代領誰的（已生效的禮品委託）。"""
        self.ensure_one()
        if not self.meeting_id or not holder:
            return self.env['assoc.member']
        return self.env['assoc.meeting.proxy'].sudo().search([
            ('meeting_id', '=', self.meeting_id.id),
            ('purpose', '=', 'gift'),
            ('state', '=', 'active'),
            ('holder_member_id', '=', holder.id),
        ]).principal_member_id


class AssocGiftItem(models.Model):
    _name = 'assoc.gift.item'
    _description = '禮品品項'
    _order = 'sequence, id'

    campaign_id = fields.Many2one(
        'assoc.gift.campaign', string='活動', required=True, ondelete='cascade', index=True)
    # related store：create 時不要傳值
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    name = fields.Char(string='品項名稱', required=True)
    delivery = fields.Selection([
        ('pickup', '現場領取'),
        ('cash_list', '現金造冊'),
        ('edenred', '宜睿禮券'),
    ], string='發放方式', required=True, default='pickup')
    unit_value = fields.Integer(string='單位金額（新台幣）')
    qty = fields.Integer(string='每人數量', default=1, required=True)
    sequence = fields.Integer(string='排序', default=10)
    entitlement_ids = fields.One2many('assoc.gift.entitlement', 'item_id', string='權利名單')

    @api.constrains('qty')
    def _check_qty(self):
        for item in self:
            if item.qty < 1:
                raise UserError(_('每人數量至少為 1。'))

    def write(self, vals):
        # 只鎖 `delivery`：它是權利列的 stored related，而且決定「現場領 vs 造冊」，
        # 改了會讓已產生的列對不上快照。
        # `unit_value` 與 `qty` **不在快照裡**——造冊時才去讀當下的值，
        # 所以金額打錯要改得動（鎖住的話只能重建名單，而重建又被「已有人領取」擋住，
        # 等於永遠改不了）。已經交出去的那份檔案是存檔的位元組，不會被追溯改寫。
        if 'delivery' in vals and any(item.entitlement_ids for item in self):
            raise AccessError(_('名單已經產生，品項的發放方式不能再改。'))
        return super().write(vals)

    def button_export(self, file_type='xlsx'):
        """造冊：產生名單檔並開啟那個批次。

        入口放在**品項**上而不是批次模型：`call_kw` 傳得了 recordset
        （`[[item_id]]`），傳不了「一個 record 當參數」的 model 方法。
        """
        self.ensure_one()
        export = self.env['assoc.gift.export'].action_export(self, file_type)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'assoc.gift.export',
            'res_id': export.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        if any(item.entitlement_ids.filtered(lambda e: e.state != 'pending') for item in self):
            raise UserError(_('已經有人領取或匯出的品項不能刪除。'))
        for item in self:
            item.entitlement_ids.with_context(**{GUARD_GIFT: GUARD}).unlink()
        return super().unlink()
