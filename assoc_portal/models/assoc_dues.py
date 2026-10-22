"""會費期別與應繳（計畫 §2.3）。

`assoc.dues` 一列＝「某位會員在某個期別應該繳多少」。收款是另一個模型
（`assoc.payment`），兩者以 `payment_id` 相連——**不另做收款明細模型**：
一筆應繳只由一筆收款付清，明細就是應繳本身（P20）。

`state` 與 `payment_id` 只能由過帳／作廢流程寫（哨兵 `assoc_dues_post`）：
出納對本模型有寫入 ACL，少了這道就能不開收據直接把自己標成已繳，
而「會費繳至」是選舉人名冊的依據。
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.assoc_base.tools import (
    GUARD, assoc_today, check_created, guarded, require_finance)

GUARD_DUES = 'assoc_dues_post'
# 只有常年會費參與「會費繳至」的連續計算
ANNUAL_TYPE = 'annual'
# 通知框裡最多列幾個「沒有 Email」的名字（其餘以「等 N 位」帶過）
NOTIFY_NAME_LIMIT = 5
# 只能由過帳／作廢流程寫的欄位
POST_FIELDS = frozenset({'state', 'payment_id'})
# 期別的鏡像欄位（related store）。related 預設 readonly → 沒有 inverse →
# 等同「沒有 inverse 的 stored compute」：寫得進去而且值會留著。
# 放著不管，有寫入 ACL 的出納就能把 date_to 改到 2030 年，
# 把「會費繳至」延長四年而且不留任何軌跡（§16 通則 7 的同一個坑）。
# ORM 重算 related 走 `_write_multi`，不經過 `write()`，不會被這道守衛擋到。
MIRROR_FIELDS = frozenset({'company_id', 'member_no', 'fee_type', 'date_from', 'date_to'})
# 建立後不可變更的身分欄位。改 `period_id` 等於把一筆**已繳**的應繳掛到另一個
# 期別（例如出納自建的、2030 才到期的那個），`fee_paid_until` 會跟著跳；
# 改 `member_id` 則是把別人繳的錢算到自己頭上。兩者都不會被 MIRROR 擋到。
IMMUTABLE_FIELDS = frozenset({'period_id', 'member_id'})


# 期別一旦產生應繳就不能再改定義。改 `date_to` 會經由 `assoc.dues` 的 related store
# 欄位一路推到每一位已繳會員的 `fee_paid_until`（選舉人名冊的依據），而且收據上
# 印的期間已經發出去了——等於不開收據就把全期所有人的會籍延長，且不留軌跡。
# `name` 與 `due_date` 不鎖：改名稱、延長繳款期限都是正常作業。
PERIOD_LOCKED_ONCE_ISSUED = frozenset({'fee_type', 'date_from', 'date_to', 'amount', 'company_id'})


class AssocDuesPeriod(models.Model):
    _name = 'assoc.dues.period'
    _description = '會費期別'
    _order = 'date_from desc, id desc'

    name = fields.Char(string='期別名稱', required=True)
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, index=True,
        default=lambda self: self.env.company)
    fee_type = fields.Selection([
        ('annual', '常年會費'),
        ('entrance', '入會費'),
        ('seminar', '研討會報名費'),
        ('other', '其他'),
    ], string='費用類型', required=True, default='annual',
        help='只有「常年會費」會納入「會費繳至」的連續計算。')
    date_from = fields.Date(string='起日', required=True)
    date_to = fields.Date(string='迄日', required=True)
    amount = fields.Integer(string='金額（新台幣）', required=True)
    due_date = fields.Date(string='繳款期限')
    state = fields.Selection([
        ('draft', '草稿'), ('open', '開放繳費'), ('closed', '已結清'),
    ], string='狀態', default='draft', required=True, readonly=True)
    dues_ids = fields.One2many('assoc.dues', 'period_id', string='應繳明細')
    dues_count = fields.Integer(string='應繳筆數', compute='_compute_stats')
    paid_count = fields.Integer(string='已繳筆數', compute='_compute_stats')
    unpaid_amount = fields.Integer(string='未收金額', compute='_compute_stats')

    _sql_constraints = [
        ('name_uniq', 'unique(company_id, name)', '同一公會的期別名稱不可重複'),
    ]

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for period in self:
            if period.date_to < period.date_from:
                raise UserError(_('期別的迄日不能早於起日。'))

    @api.constrains('fee_type', 'date_from', 'date_to', 'company_id')
    def _check_no_annual_overlap(self):
        """同一公會的常年會費期別不得重疊。

        連續計算是一期接一期往後走，兩個起日相同的期別誰先誰後會給出不同答案
        （一期已繳一期未繳時，先掃到哪一期就決定停不停）。與其讓答案取決於
        建立順序，不如讓重疊根本不存在。非常年會費不參與計算，不受此限。
        """
        for period in self.filtered(lambda p: p.fee_type == ANNUAL_TYPE):
            # sudo：這是資料完整性檢查，不是存取檢查。被 record rule 藏起來的
            # 重疊期別若查不到，連續計算就會靜默地依建立順序給答案。
            clash = self.sudo().search([
                ('id', '!=', period.id),
                ('company_id', '=', period.company_id.id),
                ('fee_type', '=', ANNUAL_TYPE),
                ('date_from', '<=', period.date_to),
                ('date_to', '>=', period.date_from),
            ], limit=1)
            if clash:
                raise UserError(_('常年會費期別不能與「%s」重疊（%s ~ %s）。',
                                  clash.name, clash.date_from, clash.date_to))

    def write(self, vals):
        locked = PERIOD_LOCKED_ONCE_ISSUED & set(vals)
        # 判準是「**有沒有應繳列**」而不是狀態：打錯日期按了「產生應繳」之後，
        # 用狀態當判準就再也改不回來（連 sudo 都不行，而且沒有回到 draft 的路）。
        # 改成看應繳列：把未繳的應繳刪掉就能修正打錯的日期，
        # 而真正的風險（已經有人依這個期間繳了錢）照樣擋住。
        if locked and any(period.dues_ids for period in self):
            raise AccessError(_('「%s」在產生應繳之後就不能再改——'
                                '已繳會員的「會費繳至」與已開出的收據都依它計算。'
                                '要調整請另開期別。', '、'.join(sorted(locked))))
        return super().write(vals)

    @api.depends('dues_ids.state', 'dues_ids.amount_due')
    def _compute_stats(self):
        for period in self:
            dues = period.dues_ids
            period.dues_count = len(dues)
            period.paid_count = len(dues.filtered(lambda d: d.state in ('paid', 'waived')))
            period.unpaid_amount = sum(dues.filtered(lambda d: d.state == 'unpaid')
                                       .mapped('amount_due'))

    def action_generate_dues(self):
        """為有效會員補建應繳列（可重複執行，只補缺的）。"""
        self.ensure_one()
        require_finance(self.env)
        if self.state == 'closed':
            raise UserError(_('已結清的期別不能再產生應繳。'))
        members = self.env['assoc.member'].search([('company_id', '=', self.company_id.id)])
        existing = set(self.dues_ids.member_id.ids)
        self.env['assoc.dues'].create([
            {'period_id': self.id, 'member_id': member.id, 'amount_due': self.amount}
            for member in members if member.id not in existing
        ])
        if self.state == 'draft':
            self.state = 'open'
        return True


    def action_close(self):
        """結清期別：年度結束後鎖住，不再產生應繳。

        未繳的留在未繳（會籍本來就該停在斷點），只是不再往裡面加人。
        """
        self.ensure_one()
        require_finance(self.env)
        if self.state != 'open':
            raise UserError(_('只有開放繳費中的期別可以結清。'))
        self.state = 'closed'
        return True

    def action_send_reminder(self):
        """為本期所有「未繳」的應繳寄提醒。

        真正的邏輯只有一份，在 `assoc.dues` 上（它才有 member_id 與 unpaid 狀態）。
        這裡只是整批入口——一筆一筆開表單按，四百人的公會按不完。
        """
        self.ensure_one()
        return self.dues_ids.action_send_reminder()

    def button_send_reminder(self):
        self.ensure_one()
        dues = self.dues_ids
        return dues._reminder_notification(dues.action_send_reminder())


class AssocDues(models.Model):
    _name = 'assoc.dues'
    _description = '應繳會費'
    _order = 'period_id desc, member_no, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    period_id = fields.Many2one(
        'assoc.dues.period', string='期別', required=True, ondelete='restrict', index=True)
    member_id = fields.Many2one(
        'assoc.member', check_company=True, string='會員', required=True, ondelete='restrict', index=True)
    # related store：create 時不要傳值
    company_id = fields.Many2one(related='period_id.company_id', store=True, index=True)
    member_no = fields.Char(related='member_id.member_no', store=True)
    member_name = fields.Char(related='member_id.name')
    fee_type = fields.Selection(related='period_id.fee_type', store=True)
    date_from = fields.Date(related='period_id.date_from', store=True)
    date_to = fields.Date(related='period_id.date_to', store=True)
    due_date = fields.Date(related='period_id.due_date')
    amount_due = fields.Integer(string='應繳金額', required=True)
    state = fields.Selection([
        ('unpaid', '未繳'), ('paid', '已繳'), ('waived', '免繳'),
    ], string='狀態', default='unpaid', required=True, readonly=True, index=True)
    payment_id = fields.Many2one(
        'assoc.payment', string='收款單', readonly=True, ondelete='restrict', index=True)
    waive_reason = fields.Char(string='免繳原因', readonly=True)
    reminder_count = fields.Integer(string='已提醒次數', readonly=True)
    last_reminder_at = fields.Datetime(string='最後提醒時間', readonly=True)
    is_overdue = fields.Boolean(string='已逾期', compute='_compute_is_overdue',
                                search='_search_is_overdue')
    # 承辦的暫存輸入（不用 wizard，本專案慣例）：按鈕讀它，不影響任何判定
    waive_input = fields.Char(string='免繳原因（輸入）')

    _sql_constraints = [
        ('period_member_uniq', 'unique(period_id, member_id)', '同一期別每位會員只有一筆應繳'),
    ]

    @api.constrains('period_id', 'member_id')
    def _check_same_company(self):
        for dues in self:
            if dues.member_id.company_id != dues.period_id.company_id:
                raise UserError(_('會員與期別必須屬於同一公會。'))

    def write(self, vals):
        if POST_FIELDS & set(vals) and not guarded(self.env, GUARD_DUES):
            raise UserError(_('繳費狀態只能由過帳、作廢或免繳動作變更。'))
        fixed = IMMUTABLE_FIELDS & set(vals)
        if fixed:
            raise AccessError(_('「%s」建立後不能變更；要改請刪掉重建（未處理的才刪得掉）。',
                                '、'.join(sorted(fixed))))
        if 'amount_due' in vals and any(dues.state != 'unpaid' for dues in self):
            raise AccessError(_('已經處理過的應繳不能改金額——收據上的金額已經凍結。'))
        mirrored = MIRROR_FIELDS & set(vals)
        if mirrored:
            raise AccessError(_('「%s」是期別或會員的鏡像欄位，要改請改來源本身。',
                                '、'.join(sorted(mirrored))))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 驗結果不驗輸入：帶 default_state='paid' 的 context 就能建出「已繳」而沒有收據
        check_created(records, {'state': 'unpaid', 'payment_id': False}, GUARD_DUES)
        return records

    def unlink(self):
        if any(dues.state != 'unpaid' or dues.payment_id for dues in self):
            raise UserError(_('已經處理過的應繳不能刪除。'))
        return super().unlink()

    def _compute_is_overdue(self):
        today = assoc_today(self)
        for dues in self:
            dues.is_overdue = bool(
                dues.state == 'unpaid' and dues.due_date and dues.due_date < today)

    def _search_is_overdue(self, operator, value):
        """非儲存 compute 沒有 search 時，篩選會靜默回傳全部。"""
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('「已逾期」只支援等於 True／False 的篩選。'))
        today = assoc_today(self)
        overdue = [('state', '=', 'unpaid'), ('due_date', '!=', False), ('due_date', '<', today)]
        wants = (operator == '=') == value
        # 否定整組條件要寫成 ['!', '&', '&', leaf, leaf, leaf]
        return overdue if wants else ['!', '&', '&', *overdue]

    def action_waive(self, reason):
        """免繳（例如年中入會、榮譽會員）。仍然算進「繳至」的連續計算。"""
        require_finance(self.env)
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('免繳必須填寫原因。'))
        for dues in self:
            if dues.state != 'unpaid':
                raise UserError(_('只有未繳的應繳可以改為免繳。'))
            if dues.payment_id:
                # 不擋的話那張草稿從此過不了帳，而且錯誤訊息會說
                # 「有應繳已經被處理過了」，與實情（被自己人改成免繳）對不上
                raise UserError(_('這筆應繳已經綁在收款單「%s」上，請先刪除那張草稿。',
                                  dues.payment_id.display_name))
        self.with_context(**{GUARD_DUES: GUARD}).write(
            {'state': 'waived', 'waive_reason': reason})
        # 免繳同樣會延長會籍，而且**不開收據**——沒有軌跡的話這是最安靜的一條路
        for dues in self:
            self.env['assoc.audit.log']._log(
                'dues_waive', records=dues.member_id, company=dues.company_id,
                detail={'dues_id': dues.id, 'period': dues.period_id.name,
                        'amount': dues.amount_due})
        return True

    def button_waive(self):
        """表單按鈕：用上面填的原因免繳。"""
        self.ensure_one()
        return self.action_waive(self.waive_input)

    # ------------------------------------------------------------------
    # 繳款提醒（信留在佇列，不真的寄出——見 assoc_base 的兩層 hold）
    # ------------------------------------------------------------------
    def _reminder_notification(self, result):
        """把結果變成通知框。

        **按鈕不能直接回傳資料 dict**：Odoo 的 `call_button` 只要收到 object
        就當成 action 用（`action_service.js`），而 `type` 是 undefined →
        前端丟「can't handle actions of type undefined」的錯誤對話框。
        交易其實已經提交，承辦看到失敗會再按一次 → 四百人就是 800 封信。
        而且「誰沒有 Email」本來就只從這個回傳值看得到。
        """
        message = _('已排入佇列 %s 封。', result['sent'])
        if result['skipped']:
            # 名單要截斷：四百人的公會可能有幾十位沒有 Email，全列會塞爆通知框
            names = result['skipped_names'][:NOTIFY_NAME_LIMIT]
            shown = '、'.join(names)
            if result['skipped'] > len(names):
                shown = _('%s 等 %s 位', shown, result['skipped'])
            message += _('\n沒有 Email、寄不出去的 %s 位：%s', result['skipped'], shown)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('繳款提醒'),
                'message': message,
                'type': 'warning' if result['skipped'] else 'success',
                'sticky': bool(result['skipped']),
            },
        }

    def button_send_reminder(self):
        return self._reminder_notification(self.action_send_reminder())

    def action_send_reminder(self):
        """寄繳款提醒。

        `force_send=False`：信件進佇列由排程寄，而排程被 `assoc.mail.hold` 攔著。
        沒有 Email 的會員跳過並在 chatter 留註記——承辦要看得出來「誰沒收到」。
        """
        require_finance(self.env)
        template = self.env.ref('assoc_portal.mail_template_dues_reminder')
        sent, skipped = self.browse(), self.browse()
        for dues in self:
            if dues.state != 'unpaid':
                continue
            if not dues.member_id.email:
                skipped |= dues
                continue
            template.send_mail(dues.id, force_send=False)
            sent |= dues
        # 計數是給對帳看的：提醒過幾次、最後一次什麼時候。
        # 逐筆加（每筆的既有次數不同），不能整批寫同一個值。
        for dues in sent:
            dues.sudo().write({
                'reminder_count': dues.reminder_count + 1,
                'last_reminder_at': fields.Datetime.now(),
            })
            # 用 `_message_log` 不是 `message_post`：後者要求作者有 Email
            # （`_message_compute_author(raise_on_email=True)`），承辦帳號常常沒有，
            # 整個提醒流程會因此掛掉。
            dues.member_id._message_log(
                body=_('已寄出「%s」的繳款提醒。', dues.period_id.name))
        for dues in skipped:
            dues.member_id._message_log(
                body=_('無法寄送「%s」的繳款提醒：這位會員沒有 Email。',
                       dues.period_id.name))
        return {'sent': len(sent), 'skipped': len(skipped),
                'skipped_names': skipped.member_id.mapped('name')}
