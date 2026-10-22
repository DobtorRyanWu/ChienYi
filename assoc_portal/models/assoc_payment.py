"""收款與收據（計畫 §2.3）。

三個關鍵取捨：

1. **綁定應繳走條件 UPDATE**，不是 ORM 寫入：`WHERE state='unpaid' AND payment_id IS NULL`
   讓兩張同時建立的草稿不會搶到同一筆應繳（後者的 rowcount 對不上就失敗）。
   條件裡一定要帶 `company_id` 與 `member_id`——少了它們，出納可以用別公會的
   應繳 id 把人家的列鎖住。

2. **狀態一律走 ORM**（帶哨兵），不用 raw SQL：`fee_paid_until` 是 stored compute，
   raw SQL 改了 `state` 它不會重算 → 退票的人還留在選舉人名冊上。
   raw SQL 只動 `payment_id`（沒有任何 compute 依賴它）。

3. **收據號用 no_gap 序號**，而且 `sequence_date` 要用**台北當日**：
   `ir_sequence` 預設取 UTC 日期（`ir_sequence.py`），台北 1/1 00:00–08:00 會落到前一年。
"""

import base64
import hashlib
from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.assoc_base.tools import (
    ASSOC_TZ, GUARD, assoc_today, check_created, guarded, require_finance)

from .assoc_dues import GUARD_DUES

GUARD_PAYMENT = 'assoc_payment_post'
# 任何狀態下都只能由過帳／作廢流程寫的欄位。
# 「草稿可以隨便改」是錯的：草稿被 RPC 寫成 posted 就占掉一個 no_gap 號碼，
# 而 no_gap 不能跳號 —— 之後每一張收據都會卡住。
SYSTEM_FIELDS = frozenset({
    'state', 'receipt_no', 'amount_total', 'posted_at', 'posted_by_uid',
    'receipt_attachment_id', 'receipt_sha256', 'void_reason', 'voided_at', 'voided_by_uid',
})
RECEIPT_REPORT = 'assoc_portal.report_receipt'
# 收據號的日期一律用台北：公會在台灣，年度編號要跟著當地日期走
RECEIPT_TZ = ASSOC_TZ          # 同一個值只留一份（見 assoc_base.tools）


class AssocPayment(models.Model):
    _name = 'assoc.payment'
    _description = '會費收款'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    name = fields.Char(string='單號', compute='_compute_name')
    company_id = fields.Many2one(
        'res.company', string='所屬公會', required=True, index=True,
        default=lambda self: self.env.company)
    # `check_company=True`：**公會 rule 檢查的是這張收款單的公會，不是
    # `member_id` 指向的那張會員的公會**。少了它，台北的出納可以在自己公會建一張
    # 收款單、把 `member_id` 指向新北的會員，再 `read(['member_id'])` 拿回
    # display_name「N001 王志明」，逐一換 id 就列舉出別家公會的完整會員名冊
    # （第十四輪 red-team 實跑）。`assoc.dues` 當時沒被打穿是**巧合**——
    # 它的 `member_no` 是 stored related，create 時必須先讀 member 才觸發 rule；
    # 這裡沒有那種護欄。全專案原本 `check_company` 命中 0 次，十個指向
    # `assoc.member` 的 m2o 一併補上（L9：同一個坑十個位置）。
    member_id = fields.Many2one(
        'assoc.member', check_company=True, string='會員', required=True, ondelete='restrict', index=True)
    payer_name = fields.Char(string='繳款人', required=True,
                             help='收據抬頭。預設為會員姓名，代繳時可改。')
    # 收款日期是**公會當地發生的事實**，不該跟著出納帳號的時區跑
    # （收據取號也是釘台北當日的，兩邊口徑要一致）。
    date = fields.Date(string='收款日期', required=True,
                       default=lambda self: assoc_today(self))
    method = fields.Selection([
        ('cash', '現金'), ('transfer', '匯款'), ('check', '支票'), ('other', '其他'),
    ], string='收款方式', default='cash', required=True)
    bank_ref = fields.Char(string='匯款末五碼／支票號碼')
    dues_ids = fields.One2many('assoc.dues', 'payment_id', string='沖銷的應繳', readonly=True)
    dues_amount = fields.Integer(string='應繳合計', compute='_compute_dues_amount')
    amount_total = fields.Integer(string='收款金額', readonly=True,
                                  help='過帳時凍結，之後不隨應繳變動。')
    state = fields.Selection([
        ('draft', '草稿'), ('posted', '已過帳'), ('voided', '已作廢'),
    ], string='狀態', default='draft', required=True, readonly=True, index=True, tracking=True)
    receipt_no = fields.Char(string='收據號碼', readonly=True, copy=False, index=True)
    posted_at = fields.Datetime(string='過帳時間', readonly=True, copy=False)
    posted_by_uid = fields.Many2one('res.users', string='經手人', readonly=True, copy=False)
    receipt_attachment_id = fields.Many2one(
        'ir.attachment', string='收據 PDF', readonly=True, copy=False, ondelete='restrict')
    receipt_sha256 = fields.Char(string='收據指紋', readonly=True, copy=False)
    void_reason = fields.Char(string='作廢原因', readonly=True, copy=False)
    voided_at = fields.Datetime(string='作廢時間', readonly=True, copy=False)
    voided_by_uid = fields.Many2one('res.users', string='作廢經手人', readonly=True, copy=False)
    # 承辦的暫存輸入（不用 wizard）：作廢按鈕讀它
    void_input = fields.Char(string='作廢原因（輸入）')

    _sql_constraints = [
        ('receipt_no_uniq', 'unique(company_id, receipt_no)', '同一公會的收據號碼不可重複'),
    ]

    def _compute_name(self):
        for payment in self:
            payment.name = payment.receipt_no or _('草稿 #%s', payment.id or '')

    @api.depends('dues_ids.amount_due')
    def _compute_dues_amount(self):
        for payment in self:
            payment.dues_amount = sum(payment.dues_ids.mapped('amount_due'))

    # ------------------------------------------------------------------
    # 守衛
    # ------------------------------------------------------------------
    def write(self, vals):
        if SYSTEM_FIELDS & set(vals) and not guarded(self.env, GUARD_PAYMENT):
            raise UserError(_('收款的狀態與收據欄位只能由過帳／作廢動作變更。'))
        if any(payment.state != 'draft' for payment in self):
            allowed = SYSTEM_FIELDS | {'void_input'}
            if set(vals) - allowed:
                raise UserError(_('過帳後的收款不能再修改。'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 驗結果不驗輸入：帶 default_state='posted' 的 context 就能建出占號的收款
        # 初值清單要**列滿**所有系統欄位：漏掉的那個就是 create 時可以塞的那個。
        # `receipt_attachment_id` 尤其重要——前台收據路由是 sudo 串流它的內容，
        # 建立時塞進別人的附件 id，日後任何一條「沒走 _store_receipt_pdf 就標成
        # posted」的路徑都會把那份檔案送給會員。
        check_created(records, {'state': 'draft', 'receipt_no': False, 'amount_total': 0,
                                'posted_at': False, 'receipt_sha256': False,
                                'receipt_attachment_id': False, 'posted_by_uid': False,
                                'void_reason': False, 'voided_at': False,
                                'voided_by_uid': False}, GUARD_PAYMENT)
        return records

    def unlink(self):
        if any(payment.state != 'draft' for payment in self):
            raise UserError(_('只有草稿可以刪除（過帳後請改用作廢，收據號碼不能消失）。'))
        for payment in self:
            payment._unbind_dues(payment.dues_ids.ids)
        return super().unlink()

    # ------------------------------------------------------------------
    # 綁定應繳
    # ------------------------------------------------------------------
    def action_bind_dues(self, dues_ids=None):
        """把未繳的應繳綁到這張草稿上。

        用條件 UPDATE：兩張同時建立的草稿不會搶到同一筆應繳（後者 rowcount 對不上）。
        """
        self.ensure_one()
        require_finance(self.env)
        if self.state != 'draft':
            raise UserError(_('只有草稿可以調整沖銷的應繳。'))
        # 先經 ORM search 過 record rule，再用 id 進 SQL
        dues = self.env['assoc.dues'].search([
            ('id', 'in', list(dues_ids or [])),
            ('member_id', '=', self.member_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'unpaid'),
        ])
        if len(dues) != len(set(dues_ids or [])):
            raise UserError(_('有應繳不屬於這位會員、或已經被處理過了。'))
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE assoc_dues SET payment_id = %s
             WHERE id = ANY(%s) AND company_id = %s AND member_id = %s
               AND state = 'unpaid' AND payment_id IS NULL
             RETURNING id
        """, [self.id, dues.ids, self.company_id.id, self.member_id.id])
        bound = self.env.cr.fetchall()
        if len(bound) != len(dues):
            raise UserError(_('有應繳剛剛被別人綁走了，請重新整理後再試。'))
        # raw SQL 只動 payment_id（沒有 compute 依賴它），之後讓快取失效
        self.env['assoc.dues'].invalidate_model(['payment_id'])
        return True

    def _unbind_dues(self, dues_ids):
        if not dues_ids:
            return
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE assoc_dues SET payment_id = NULL WHERE id = ANY(%s) AND payment_id = %s",
            [list(dues_ids), self.id])
        self.env['assoc.dues'].invalidate_model(['payment_id'])

    # ------------------------------------------------------------------
    # 過帳
    # ------------------------------------------------------------------
    def action_post(self):
        """過帳：應繳轉已繳 → 取收據號 → 產 PDF 存檔。"""
        self.ensure_one()
        require_finance(self.env)
        if self.state != 'draft':
            raise UserError(_('只有草稿可以過帳。'))
        dues = self.dues_ids
        if not dues:
            raise UserError(_('請先選擇要沖銷的應繳。'))
        if any(one.state != 'unpaid' for one in dues):
            raise UserError(_('有應繳已經被處理過了，請重新整理後再試。'))
        # 綁定之後 member_id 還能改（草稿可編輯），所以過帳當下要再確認一次
        if any(one.member_id != self.member_id or one.company_id != self.company_id
               for one in dues):
            raise UserError(_('沖銷的應繳必須屬於這位會員。'))

        # state 走 ORM：`fee_paid_until` 是 stored compute，raw SQL 改了它不會重算
        dues.with_context(**{GUARD_DUES: GUARD}).write({'state': 'paid'})
        self.with_context(**{GUARD_PAYMENT: GUARD}).write({
            'state': 'posted',
            'amount_total': sum(dues.mapped('amount_due')),
            'receipt_no': self._next_receipt_no(),
            'posted_at': fields.Datetime.now(),
            'posted_by_uid': self.env.uid,
        })
        self._store_receipt_pdf()
        self.env['assoc.audit.log']._log(
            'receipt_post', records=self.member_id, company=self.company_id,
            detail={'payment_id': self.id, 'receipt_no': self.receipt_no,
                    'amount': self.amount_total, 'sha256': self.receipt_sha256})
        return True

    def _next_receipt_no(self):
        """每個公會一條 no_gap 序號；日期用台北當日。"""
        self.ensure_one()
        sequence = self.company_id.sudo().assoc_receipt_sequence_id
        if not sequence:
            sequence = self.env['ir.sequence'].sudo().create({
                'name': '%s 收據號碼' % self.company_id.name,
                'code': 'assoc.payment.receipt.%s' % self.company_id.id,
                'implementation': 'no_gap',
                'prefix': '%(range_year)s-',
                'padding': 5,
                'use_date_range': True,
                'company_id': self.company_id.id,
            })
            self.company_id.sudo().assoc_receipt_sequence_id = sequence
        today_taipei = datetime.now(pytz.timezone(RECEIPT_TZ)).date()
        return sequence.next_by_id(sequence_date=today_taipei)

    def _store_receipt_pdf(self):
        """產一次 PDF 存起來：之後重印一律給存檔，不重算（金額與抬頭要凍結）。"""
        self.ensure_one()
        report = self.env['ir.actions.report'].sudo()
        if report.get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            raise UserError(_('PDF 產生器目前不可用，請洽系統管理員後再過帳。'))
        pdf, _content_type = report._render_qweb_pdf(RECEIPT_REPORT, res_ids=self.ids)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': '收據-%s.pdf' % self.receipt_no,
            'type': 'binary',
            'datas': base64.b64encode(pdf),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        self.with_context(**{GUARD_PAYMENT: GUARD}).write({
            'receipt_attachment_id': attachment.id,
            'receipt_sha256': hashlib.sha256(pdf).hexdigest(),
        })

    # ------------------------------------------------------------------
    # 作廢
    # ------------------------------------------------------------------
    def action_void(self, reason=None):
        """作廢：應繳退回未繳並解綁（可以重開新收款），收據存檔保留。"""
        self.ensure_one()
        require_finance(self.env)
        reason = (reason if reason is not None else self.void_input) or ''
        reason = reason.strip()
        if not reason:
            raise UserError(_('作廢必須填寫原因。'))
        if self.state != 'posted':
            raise UserError(_('只有已過帳的收款可以作廢。'))
        dues = self.dues_ids
        # 走 ORM 讓 `fee_paid_until` 重算：用 raw SQL 的話，退票的人還留在選舉人名冊上
        dues.with_context(**{GUARD_DUES: GUARD}).write({'state': 'unpaid'})
        self._unbind_dues(dues.ids)
        self.with_context(**{GUARD_PAYMENT: GUARD}).write({
            'state': 'voided',
            'void_reason': reason,
            'voided_at': fields.Datetime.now(),
            'voided_by_uid': self.env.uid,
        })
        self.env['assoc.audit.log']._log(
            'receipt_void', records=self.member_id, company=self.company_id,
            detail={'payment_id': self.id, 'receipt_no': self.receipt_no,
                    'sha256': self.receipt_sha256})
        return True

    def button_void(self):
        self.ensure_one()
        return self.action_void()

    def action_print_receipt(self):
        """重印：一律給存檔的那份，不重算。"""
        self.ensure_one()
        if not self.receipt_attachment_id:
            raise UserError(_('這張收款還沒有收據存檔。'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.receipt_attachment_id.id,
            'target': 'self',
        }
