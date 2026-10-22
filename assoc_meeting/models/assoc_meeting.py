"""會員大會與研討會（計畫 §6、§7、§8、P11）。

同一個模型兩種性質，用 `kind` 分：
- `assembly` 會員大會：有法定人數、可以有委託出席（人團法 §38）、沒有簽退。
- `seminar` 研討會：有簽退與積分，沒有法定人數也不能建選舉。

`state` 與 `kind` 的寫入一律要哨兵（§16 通則 1–2）：`call_kw` 會把前端送來的
context 直接套進 env（`odoo/api.py:531-532`），所以「context 旗標為真」擋不住
任何有寫入 ACL 的角色——報到台一行 RPC 就能把大會改成開放報到。
"""

import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.assoc_base.tools import GUARD, check_created, check_guild_admin, guarded

_logger = logging.getLogger(__name__)

# 報到台最近報到清單顯示筆數
RECENT_CHECKIN_LIMIT = 10
GUARD_STATE = 'assoc_meeting_state'
# 只能由狀態流轉方法寫的欄位
STATE_FIELDS = frozenset({'state', 'kind'})
# 開放報到後不可再改的設定：改了會讓**已經發生的事**判定跟著變。
# `date_begin` 一定要在裡面——遲到的判定就是 `date_begin + grace`，
# 而散會時會自動重算，改一個欄位就能把 0 分變滿分。
# `quorum_ratio` 同理：法定人數是即時 compute，沒有決議時點的快照。
# `approval_ref`（認可文號）刻意**不鎖**：文號實務上常常是活動結束後才下來。
LOCKED_AFTER_DRAFT = frozenset({
    'date_begin', 'date_end', 'quorum_ratio', 'checkin_grace_min', 'checkout_open_min',
    'credit_points', 'credit_hours', 'credit_category', 'require_dynamic_pass',
})


class AssocMeeting(models.Model):
    _name = 'assoc.meeting'
    _description = '會員大會'
    _inherit = ['mail.thread']
    _order = 'date_begin desc, id desc'

    name = fields.Char(string='會議名稱', required=True, tracking=True)
    kind = fields.Selection([
        ('assembly', '會員大會'),
        ('seminar', '研討會'),
    ], string='性質', default='assembly', required=True, tracking=True,
        help='會員大會有法定人數與委託出席；研討會有簽退與積分。建立後不可變更。')
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, tracking=True,
        default=lambda self: self.env.company)
    date_begin = fields.Datetime(string='開會時間', required=True, tracking=True)
    place = fields.Char(string='地點')
    quorum_ratio = fields.Float(
        string='法定出席比例', default=0.5, tracking=True,
        help='出席（含委託）人數須「超過」出席名冊人數乘以此比例（0.5 即過半數）。')
    state = fields.Selection([
        ('draft', '籌備中'),
        ('checkin_open', '開放報到'),
        ('in_session', '開會中'),
        ('closed', '已散會'),
    ], string='狀態', default='draft', required=True, readonly=True, copy=False, tracking=True)
    attendance_ids = fields.One2many('assoc.meeting.attendance', 'meeting_id', string='出席名冊')
    member_count = fields.Integer(string='名冊人數', compute='_compute_attendance_stats')
    present_count = fields.Integer(string='親自出席', compute='_compute_attendance_stats')
    proxy_count = fields.Integer(string='委託出席', compute='_compute_attendance_stats')
    quorum_met = fields.Boolean(string='達法定人數', compute='_compute_attendance_stats')

    # ---- 研討會（kind='seminar'）----
    date_end = fields.Datetime(string='結束時間', help='研討會必填：簽退時窗與積分判定都以它為準。')
    checkin_grace_min = fields.Integer(
        string='遲到寬限（分）', default=15,
        help='開始後超過這個時間才報到 → 積分判定為遲到。')
    checkout_open_min = fields.Integer(
        string='提前開放簽退（分）', default=10,
        help='結束前這段時間就可以簽退（散場動線）。')
    credit_points = fields.Integer(string='積分', help='由承辦依認可公文填寫，系統不自動換算。')
    credit_hours = fields.Float(string='時數')
    credit_category = fields.Selection([
        ('technical', '專業技術'),
        ('procurement', '採購'),
        ('law', '法規'),
        ('ethics', '職業倫理'),
    ], string='積分類別')
    approval_ref = fields.Char(string='認可文號')
    require_dynamic_pass = fields.Boolean(
        string='只收動態報到碼',
        help='勾選後不接受靜態會員卡。跨公會會員在第二家沒有前台帳號，只能手動簽到。')

    # ---- 委託出席（kind='assembly'）----
    proxy_deadline = fields.Datetime(
        string='委託截止', tracking=True, help='會員前台可以設定委託的最後時間。')
    proxy_serial = fields.Integer(
        string='委託序號', default=0, readonly=True, copy=False,
        help='只由生效流程以 raw SQL 遞增，用來序列化 1/3 上限的判定。')

    # ------------------------------------------------------------------
    # 守衛
    # ------------------------------------------------------------------
    def write(self, vals):
        if STATE_FIELDS & set(vals) and not guarded(self.env, GUARD_STATE):
            raise UserError(_('大會狀態與性質只能由狀態流轉動作變更。'))
        locked = LOCKED_AFTER_DRAFT & set(vals)
        if locked and any(meeting.state != 'draft' for meeting in self):
            raise UserError(_('開放報到後不能再調整這些設定（%s）：已經發生的報到與積分'
                              '判定會跟著變。', ', '.join(sorted(locked))))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        meetings = super().create(vals_list)
        # 驗結果不驗輸入：context 的 default_state 與自建的 ir.default 都會改初值
        check_created(meetings, {'state': 'draft', 'proxy_serial': 0}, GUARD_STATE)
        return meetings

    def unlink(self):
        """attendance 是 cascade：刪大會可以整批帶走出席紀錄，繞過出席守衛。"""
        attending = self.env['assoc.meeting.attendance'].sudo().search_count([
            ('meeting_id', 'in', self.ids), ('state', '!=', 'absent')])
        if attending:
            raise UserError(_('已經有人報到的會議不能刪除，請改為散會。'))
        return super().unlink()

    @api.constrains('kind', 'date_begin', 'date_end')
    def _check_seminar_fields(self):
        for meeting in self:
            if meeting.kind != 'seminar':
                continue
            if not meeting.date_end:
                raise ValidationError(_('研討會必須填結束時間（簽退與積分都以它為準）。'))
            if meeting.date_end <= meeting.date_begin:
                raise ValidationError(_('研討會的結束時間必須晚於開始時間。'))

    # ------------------------------------------------------------------
    # 統計
    # ------------------------------------------------------------------
    @api.depends('attendance_ids.state', 'quorum_ratio')
    def _compute_attendance_stats(self):
        counts = defaultdict(lambda: defaultdict(int))
        real_ids = [meeting._origin.id for meeting in self if meeting._origin.id]
        if real_ids:
            groups = self.env['assoc.meeting.attendance']._read_group(
                [('meeting_id', 'in', real_ids)], ['meeting_id', 'state'], ['__count'])
            for meeting, state, count in groups:
                counts[meeting.id][state] += count
        for meeting in self:
            # 表單 onchange 時是 NewId，統計要用原始紀錄的 id
            by_state = counts[meeting._origin.id]
            meeting.member_count = sum(by_state.values())
            meeting.present_count = by_state['present']
            meeting.proxy_count = by_state['proxy']
            attending = meeting.present_count + meeting.proxy_count
            meeting.quorum_met = bool(meeting.member_count) and attending > meeting.member_count * meeting.quorum_ratio

    # ------------------------------------------------------------------
    # 狀態流轉
    # ------------------------------------------------------------------
    def _set_state(self, new_state, allowed_from):
        for meeting in self:
            if meeting.state not in allowed_from:
                raise UserError(_('「%(name)s」目前狀態不能執行此動作', name=meeting.name))
        self.with_context(**{GUARD_STATE: GUARD}).write({'state': new_state})

    def action_build_roster(self):
        """依會員名冊補建出席名冊（只補缺漏者，可重複執行）。停權會員不列入。"""
        Attendance = self.env['assoc.meeting.attendance']
        for meeting in self:
            if meeting.state == 'closed':
                raise UserError(_('已散會的大會不能再調整出席名冊'))
            members = self.env['assoc.member'].search([('company_id', '=', meeting.company_id.id)])
            existing = set(meeting.attendance_ids.member_id.ids)
            Attendance.create([
                {'meeting_id': meeting.id, 'member_id': member.id}
                for member in members if member.id not in existing
            ])
        return True

    def action_open_checkin(self):
        for meeting in self.filtered(lambda m: not m.attendance_ids):
            meeting.action_build_roster()
        self._set_state('checkin_open', ('draft',))

    def action_start_session(self):
        """開會前先把候補委託依序處理掉，再確認 1/3 上限仍成立。"""
        for meeting in self.filtered(lambda m: m.kind == 'assembly'):
            meeting._activate_waiting_proxies()
            meeting._assert_proxy_ratio()
        self._set_state('in_session', ('checkin_open',))

    def action_close_meeting(self):
        self._set_state('closed', ('checkin_open', 'in_session'))
        for meeting in self.filtered(lambda m: m.kind == 'seminar'):
            meeting.action_recompute_credits()

    def action_export_credits(self, file_type='xlsx', reveal=False):
        """匯出積分名冊（預設遮蔽身分證；明文要另外指定並會寫 export_pii 軌跡）。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/assoc/meeting/%s/credits/export?file_type=%s&reveal=%s' % (
                self.id, file_type, '1' if reveal else '0'),
            'target': 'self',
        }

    def action_open_desk(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/assoc/desk/{self.id}', 'target': 'new'}

    # ------------------------------------------------------------------
    # 委託（§7）
    # ------------------------------------------------------------------
    def _activate_waiting_proxies(self):
        """依受託人的報到時間 FIFO 處理候補委託。

        每一件各包一個 savepoint：只攔唯一索引違反與業務例外，
        **40001／55P03／40P01 一律往外拋**交給核心的 `retrying` 重跑整個請求
        （吞掉它們的話，交易已經壞掉還繼續做下一件，後面全部靜默失敗）。
        """
        from psycopg2.errors import UniqueViolation
        self.ensure_one()
        pending = self.env['assoc.meeting.proxy'].sudo().search([
            ('meeting_id', '=', self.id), ('purpose', '=', 'attend'),
            ('state', 'in', ('requested', 'waiting')),
        ])
        # FIFO：受託人先到場的先處理（沒報到的排在最後，他們本來就過不了）
        holder_checkin = {
            att.member_id.id: att.checkin_at
            for att in self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', self.id), ('state', '=', 'present')])
        }
        far_future = fields.Datetime.to_datetime('2999-12-31 00:00:00')
        pending = pending.sorted(
            lambda p: (holder_checkin.get(p.holder_member_id.id) or far_future, p.requested_at or far_future, p.id))
        results = []
        for proxy in pending:
            if not proxy._paper_gate_open():
                continue
            try:
                with self.env.cr.savepoint():
                    results.append((proxy.id, proxy._try_activate()))
            except (UniqueViolation, UserError, ValidationError) as err:
                # 只攔這三種（§16 通則 4）。40001／55P03／40P01 不在清單裡，
                # 會自己往外拋給核心的 `retrying` 重跑整個請求——
                # 「不攔」就是實作方式，不需要再寫一個兩個分支都 raise 的 except。
                results.append((proxy.id, 'failed'))
                _logger.info('委託 %s 生效失敗：%s', proxy.id, err)
        return results

    def _assert_proxy_ratio(self):
        """開會前再確認一次 1/3。

        直接查資料庫，不讀 `proxy_count`／`present_count`：那兩個是 compute，
        而委託生效走的是 raw SQL，`invalidate_model` 只失效指定欄位、
        **不會**連帶失效依賴它們的 compute（`models.py` 的 `_invalidate_cache`
        不觸發 `modified`）。讀快取的話這道閘門會分不出「通過」與「量到舊數字」。
        """
        from .assoc_meeting_proxy import PROXY_RATIO_DIVISOR
        self.ensure_one()
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT count(*) FILTER (WHERE state = 'present'),
                   count(*) FILTER (WHERE state = 'proxy')
              FROM assoc_meeting_attendance
             WHERE meeting_id = %s AND company_id = %s
        """, [self.id, self.company_id.id])
        present, proxied = self.env.cr.fetchone()
        if PROXY_RATIO_DIVISOR * proxied > present:
            raise UserError(_(
                '委託出席 %(proxy)s 人超過親自出席 %(present)s 人的三分之一，不能開會。',
                proxy=proxied, present=present))
        return True

    def action_recompute_credits(self):
        """重算全場積分（已人工調整過的跳過）。

        view 上的 `groups=` 只擋按鈕、擋不了 RPC；報到台對 attendance 有寫入 ACL，
        少了這道就能重寫全場積分。
        """
        self.ensure_one()
        # 群組 ∧ 公會走共用的那一支：手刻就是第八份複製品（L9）。
        # 原本只驗群組，而它擋得住別家公會純屬巧合——靠的是下一行剛好讀了 `self.kind`。
        check_guild_admin(self, _('只有公會管理員可以重算積分。'))
        if self.kind != 'seminar':
            raise UserError(_('只有研討會才有積分。'))
        self.attendance_ids._recompute_credit()
        return True

    # ------------------------------------------------------------------
    # 報到台資料
    # ------------------------------------------------------------------
    def _desk_poll_data(self):
        self.ensure_one()
        recent = self.env['assoc.meeting.attendance'].search(
            [('meeting_id', '=', self.id), ('state', 'in', ('present', 'proxy'))],
            order='checkin_at desc, id desc', limit=RECENT_CHECKIN_LIMIT)
        return {
            'state': self.state,
            'kind': self.kind,
            'member_count': self.member_count,
            'present_count': self.present_count,
            'proxy_count': self.proxy_count,
            'quorum_met': self.quorum_met,
            'recent': [att._desk_info() for att in recent],
        }
