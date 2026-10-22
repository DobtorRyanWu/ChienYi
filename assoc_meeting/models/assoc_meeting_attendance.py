"""出席紀錄：報到、簽退、委託、研討會積分（計畫 §6、§7、§8）。

寫入守衛是**白名單**：建立之後，任何欄位的 write 都必須帶對應的哨兵物件。
用「有沒有這個 context 旗標」當守衛擋不住任何人——`call_kw` 會把前端送來的
context 直接套進 env（`odoo/api.py:531-532`），報到台一行 RPC 就能偽造積分或
把自己改成委託出席而繞過 1/3 上限。哨兵是模組內的 Python 物件，JSON 造不出來。

（stored related 的 `company_id`／`member_no` 不受影響：核心刷新它們走
`_write_multi`（`models.py:6852`），不經過 `write()`。）
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.image import image_data_uri

from odoo.addons.assoc_base.tools import (
    GUARD, PASS_TOKEN_RE, PROXY_CODE_RE, check_created, check_guild_admin, guarded,
    verify_pass_token)

# 會員卡條碼是 64 bit 十進位字串，最長 20 位；超過就不必查庫
MAX_BARCODE_DIGITS = 20
# 結束後還能補簽退的上限（分）。超過只能由管理員後台補登。
CHECKOUT_CLOSE_MIN = 120
ADMIN_GROUP = 'assoc_base.group_assoc_admin'

GUARD_CHECKIN = 'assoc_checkin'
GUARD_CREDIT = 'assoc_credit'
# 白名單：每個可寫欄位都要指定是哪一道流程負責
CHECKIN_FIELDS = frozenset({
    'state', 'checkin_at', 'checkin_method', 'checkin_by_uid', 'manual_reason',
    'proxy_id', 'checkout_at', 'checkout_method', 'checkout_by_uid', 'checkout_reason',
})
CREDIT_FIELDS = frozenset({'credit_status', 'credit_points', 'credit_note', 'credit_overridden'})
# 承辦的暫存輸入：不是狀態、沒有任何閘門讀它，所以不需要哨兵
INPUT_FIELDS = frozenset({'input_checkout_at', 'input_reason',
                          'input_credit_status', 'input_credit_points'})
OPEN_MEETING_STATES = ('checkin_open', 'in_session')


def _minutes(value):
    return timedelta(minutes=value or 0)


class AssocMeetingAttendance(models.Model):
    _name = 'assoc.meeting.attendance'
    _description = '會員大會出席紀錄'
    _order = 'meeting_id, member_no, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    meeting_id = fields.Many2one('assoc.meeting', string='大會', required=True, ondelete='cascade', index=True)
    member_id = fields.Many2one('assoc.member', check_company=True, string='會員', required=True, ondelete='restrict', index=True)
    # related store：create 時不要傳值（readonly related 會寫回來源）
    company_id = fields.Many2one(related='meeting_id.company_id', store=True, index=True)
    member_no = fields.Char(related='member_id.member_no', store=True)
    member_name = fields.Char(string='姓名', related='member_id.name')
    meeting_kind = fields.Selection(related='meeting_id.kind')
    state = fields.Selection([
        ('absent', '未到'),
        ('present', '親自出席'),
        ('proxy', '委託出席'),
    ], string='出席狀態', default='absent', required=True, readonly=True)
    checkin_at = fields.Datetime(string='報到時間', readonly=True)
    checkin_method = fields.Selection([
        ('qr_static', '掃會員卡'),
        ('manual', '手動簽到'),
        ('qr_dynamic', '動態 QR'),
        ('proxy', '委託代簽'),
    ], string='報到方式', readonly=True)
    checkin_by_uid = fields.Many2one('res.users', string='報到經手人', readonly=True)
    manual_reason = fields.Char(string='手動簽到原因', readonly=True)
    proxy_id = fields.Many2one('assoc.meeting.proxy', string='委託書', readonly=True, ondelete='set null')

    # ---- 研討會簽退與積分 ----
    checkout_at = fields.Datetime(string='簽退時間', readonly=True)
    checkout_method = fields.Selection([
        ('qr_static', '掃會員卡'),
        ('qr_dynamic', '動態 QR'),
        ('manual', '後台補登'),
    ], string='簽退方式', readonly=True)
    checkout_by_uid = fields.Many2one('res.users', string='簽退經手人', readonly=True)
    checkout_reason = fields.Char(string='補登原因', readonly=True)
    credit_status = fields.Selection([
        ('pending', '未判定'),
        ('eligible', '符合'),
        ('late', '遲到'),
        ('no_checkout', '未簽退'),
        ('early_leave', '提前離場'),
        ('absent', '未出席'),
    ], string='積分判定', default='pending', readonly=True)
    credit_points = fields.Integer(string='積分', readonly=True)
    credit_note = fields.Char(string='積分備註', readonly=True)
    credit_overridden = fields.Boolean(
        string='已人工調整', readonly=True, copy=False,
        help='人工調整過的紀錄，之後重算會跳過。')

    # ---- 承辦的暫存輸入（不是狀態，只是按鈕要讀的值）----
    # 不用 wizard（本專案慣例），所以補登與調整的參數放在紀錄上由按鈕讀取。
    # 這些欄位不影響任何判定，改它們不需要哨兵；真正的驗證在 action_* 裡。
    input_checkout_at = fields.Datetime(string='補登簽退時間')
    input_reason = fields.Char(string='原因')
    input_credit_status = fields.Selection(
        [('eligible', '符合'), ('late', '遲到'), ('no_checkout', '未簽退'),
         ('early_leave', '提前離場'), ('absent', '未出席')], string='調整為')
    input_credit_points = fields.Integer(string='調整積分')

    _sql_constraints = [
        ('meeting_member_uniq', 'unique(meeting_id, member_id)', '同一會員在同一場大會只能有一筆出席紀錄'),
    ]

    @api.constrains('meeting_id', 'member_id')
    def _check_same_company(self):
        for att in self:
            if att.member_id.company_id != att.meeting_id.company_id:
                raise ValidationError(_('會員與大會必須屬於同一公會'))

    # ------------------------------------------------------------------
    # 守衛
    # ------------------------------------------------------------------
    def write(self, vals):
        touched = set(vals)
        if touched & CHECKIN_FIELDS and not guarded(self.env, GUARD_CHECKIN):
            raise UserError(_('出席與簽退只能透過報到台或補登動作變更。'))
        if touched & CREDIT_FIELDS and not guarded(self.env, GUARD_CREDIT):
            raise UserError(_('積分只能由重算或人工調整動作變更。'))
        unknown = touched - CHECKIN_FIELDS - CREDIT_FIELDS - INPUT_FIELDS
        if unknown:
            raise UserError(_('出席紀錄不允許直接修改：%s', ', '.join(sorted(unknown))))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 驗結果不驗輸入：帶 default_state='present' 的 context 或自建 ir.default
        # 都能讓「只看 vals」的守衛整個失效（§16 通則 1）
        # 受守衛的欄位要**全部**列出來：漏一個就等於在 create 開了一條無軌跡的後門
        # （例如直接建出 state='absent' 卻 credit_status='eligible' 的紀錄，
        #  前台就會憑它核發「茲證明全程參與」的積分證明）
        check_created(records, dict.fromkeys(CHECKIN_FIELDS | CREDIT_FIELDS, False)
                      | {'state': 'absent', 'credit_status': 'pending', 'credit_points': 0},
                      GUARD_CHECKIN)
        return records

    def unlink(self):
        if any(att.state != 'absent' for att in self):
            raise UserError(_('已經報到的紀錄不能刪除（出席是法定人數的依據）。'))
        return super().unlink()

    def _check_admin(self):
        check_guild_admin(self)   # 訊息＝預設值，不重複寫一次

    # ------------------------------------------------------------------
    # 掃碼分流（§6）
    # ------------------------------------------------------------------
    @api.model
    def _checkin_by_code(self, meeting, code):
        r"""報到台掃到的東西一律進這裡分流：靜態會員卡、動態報到碼、委託書、其他。

        長度是唯一的判準：會員卡是 ≤20 位十進位，動態碼固定 30 位。

        擋住全形數字的是 `PASS_TOKEN_RE` 的 `[0-9]`（只吃 ASCII），不是這裡的
        `isascii()`：`\d` 會吃全形、`int()` 也吃（`int('２２２')` == 222），
        於是「真會員 id ＋ 全形 MAC」會一路走到 `hmac.compare_digest`，
        而它對非 ASCII 字串丟 TypeError → 整條路由 500（實測）。
        這裡的 `isascii()` 只是省掉一次註定查不到的條碼查詢。
        """
        if meeting.state not in OPEN_MEETING_STATES:
            return {'status': 'not_open'}
        # JSON 送得進來的不只字串：數字、陣列、null 都可能。
        # 不先收斂型別的話，`.strip()` 會丟 AttributeError 變成 500。
        if not isinstance(code, str):
            return {'status': 'invalid'}
        code = code.strip()
        if PASS_TOKEN_RE.match(code):
            return self._scan_dynamic(meeting, code)
        # **委託書要排在靜態卡之前**：靜態卡那一支的條件是「≤20 位純數字」，
        # 而委託書是 24 位——雖然 24 > 20 不會被它吃掉，順序仍然寫在前面，
        # 因為一旦有人放寬 `MAX_BARCODE_DIGITS`，排在後面就會被靜默吃掉。
        if PROXY_CODE_RE.match(code):
            return self._scan_proxy(meeting, code)
        if code.isascii() and code.isdigit() and len(code) <= MAX_BARCODE_DIGITS:
            return self._scan_static(meeting, code)
        return {'status': 'invalid'}

    @api.model
    def _scan_proxy(self, meeting, code):
        """掃到一張委託書。**唯讀、不寫任何欄位、不回 `member_id`。**

        不回 `member_id` 是這支最重要的一件事：`desk.py` 的 `_with_desk_context`
        看到回應裡有 `member_id` 就會鑄一個 `desk_ref`，而 `desk_ref(source='scan')`
        是**禮品領取**的「卡被掃過」憑證。回了它，翻拍一張委託單就能換到
        受託人的禮品代領憑證。所以受託人那一邊用 `holder_member_id` 這個鍵名。

        也不翻 `paper_received`：掃碼只是查詢加速器，不是授權。
        書面閘門永遠由承辦當著人按下確認鍵才翻（`/proxy/receive`）。
        """
        proxy = self.env['assoc.meeting.proxy']._by_form_code(code)
        if not proxy:
            # 形狀對但查不到／hash 不符：一律 invalid，不透露那個 id 存不存在
            return {'status': 'invalid'}
        if proxy.meeting_id != meeting:
            # **不回大會名稱**：`_by_form_code` 走 sudo，所以這裡讀得到別家公會的
            # 大會——回了名稱就是把 ORM 讀不到的資料經掃碼端點漏出去。
            return {'status': 'proxy_other_meeting'}
        if proxy.state == 'active':
            return {'status': 'proxy_already_active', 'proxy': proxy._desk_payload()}
        # `waiting` 與 `superseded` **不可以併進 `proxy_closed`**：
        #   * `waiting`＝候補（受託人已代理 1 人），`action_start_session` 會
        #     再跑一次 `_activate_waiting_proxies()`——它是活的，而且前台還給印。
        #   * `superseded`＝委託人本人已到場，不是「取消或退回」。
        # 併在一起的後果不是措辭難看：橫幅那句話是承辦唸給會員聽的，
        # 而唸完之後重新登錄會撞 `assoc_proxy_principal` 這條 unique index，
        # 報到台就卡在那裡——而那張委託書其實自己會生效。
        if proxy.state == 'waiting':
            return {'status': 'proxy_waiting', 'proxy': proxy._desk_payload()}
        if proxy.state == 'superseded':
            return {'status': 'proxy_superseded', 'proxy': proxy._desk_payload()}
        if proxy.state != 'requested':
            return {'status': 'proxy_closed', 'proxy': proxy._desk_payload(),
                    'reason': proxy.cancel_reason or ''}
        return {'status': 'proxy_found', 'proxy': proxy._desk_payload()}

    @api.model
    def _checkin_by_barcode(self, meeting, barcode):
        """`_checkin_by_code` 的舊名（選舉模組的測試還在用）。

        它**不是**「只收靜態卡」的入口——行為與新名字完全相同，動態碼一樣會分流。
        """
        return self._checkin_by_code(meeting, barcode)

    @api.model
    def _scan_static(self, meeting, barcode):
        if meeting.require_dynamic_pass:
            return {'status': 'static_not_allowed'}
        # 條碼欄位只有公會管理員讀得到，查詢用 sudo；大會的存取權已由呼叫端（報到台守衛）確認過
        attendance = self.sudo().search(
            [('meeting_id', '=', meeting.id), ('member_id.barcode', '=', barcode)], limit=1)
        if not attendance:
            return {'status': 'invalid'}
        return attendance.with_env(self.env)._scan_action('qr_static')

    @api.model
    def _scan_dynamic(self, meeting, code):
        member, verdict = verify_pass_token(self.env, code)
        if verdict == 'invalid':
            return {'status': 'invalid'}
        attendance = self.sudo().search(
            [('meeting_id', '=', meeting.id), ('member_id', '=', member.id)], limit=1)
        if not attendance:
            return {'status': 'invalid'}
        attendance = attendance.with_env(self.env)
        if verdict == 'expired':
            # MAC 對得上才回過期：不然「這個會員存在但碼過期了」本身就是情報
            return {'status': 'pass_expired', **attendance._desk_info()}
        return attendance._scan_action('qr_dynamic')

    def _scan_action(self, method):
        """同一次掃碼在大會是報到、在研討會可能是報到也可能是簽退。"""
        self.ensure_one()
        if self.meeting_id.kind != 'seminar':
            return self._checkin(method)
        if self.state == 'absent':
            return self._checkin(method)
        if self.checkout_at:
            return {'status': 'already_out', **self._desk_info()}
        window = self._checkout_window()
        now = self.env.cr.now()
        if now < window[0]:
            # 真的提前離場由管理員事後補登；這裡不寫入，避免散場前的誤掃變成提前離場
            return {'status': 'checkout_early', **self._desk_info()}
        if now > window[1]:
            return {'status': 'checkout_closed', **self._desk_info()}
        return self._checkout(method)

    def _checkout_window(self):
        """(最早可簽退, 最晚可簽退)。"""
        self.ensure_one()
        meeting = self.meeting_id
        return (meeting.date_end - _minutes(meeting.checkout_open_min),
                meeting.date_end + _minutes(CHECKOUT_CLOSE_MIN))

    # ------------------------------------------------------------------
    # 報到與簽退
    # ------------------------------------------------------------------
    def _checkin_manual(self, reason):
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('手動簽到必須填寫原因'))
        if self.meeting_id.state not in OPEN_MEETING_STATES:
            return {'status': 'not_open'}
        return self._checkin('manual', reason)

    def _checkin(self, method, reason=False):
        """已出席者回 already；併發重複報到由 REPEATABLE READ 的 40001 + retrying 收斂成 already。"""
        self.ensure_one()
        if self.state == 'proxy':
            # 委託人後來親自到場：改成親自出席、委託書標記本人到場。
            # 方向是安全的——proxy 減一、present 加一，1/3 不會因此被打破。
            self._supersede_proxy()
        elif self.state != 'absent':
            return {'status': 'already', **self._desk_info()}
        self.with_context(**{GUARD_CHECKIN: GUARD}).write({
            'state': 'present',
            'checkin_at': self.env.cr.now(),
            'checkin_method': method,
            'checkin_by_uid': self.env.uid,
            'manual_reason': reason,
        })
        return {'status': 'confirmed', **self._desk_info()}

    def _supersede_proxy(self):
        """本人到場：委託書自己把出席紀錄退回並標記 superseded。

        寫入交給 `assoc.meeting.proxy` 做，這裡不需要（也不應該）知道它的哨兵名字。
        """
        self.ensure_one()
        proxy = self.sudo().proxy_id
        if proxy:
            proxy._supersede()
        return True

    def _checkout(self, method, at=None, reason=False):
        self.ensure_one()
        self.with_context(**{GUARD_CHECKIN: GUARD}).write({
            'checkout_at': at or self.env.cr.now(),
            'checkout_method': method,
            'checkout_by_uid': self.env.uid,
            'checkout_reason': reason,
        })
        return {'status': 'checked_out', **self._desk_info()}

    def action_manual_checkout(self, checkout_at, reason):
        """後台補登簽退（例：真的提前離場、掃碼失敗）。"""
        self.ensure_one()
        self._check_admin()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('補登簽退必須填寫原因。'))
        if self.state != 'present':
            raise UserError(_('只有已報到的紀錄可以補登簽退。'))
        meeting = self.meeting_id
        latest = meeting.date_end + _minutes(CHECKOUT_CLOSE_MIN)
        if not (meeting.date_begin <= checkout_at <= latest):
            raise UserError(_('補登的簽退時間必須落在會議開始到結束後 %s 分鐘之間。',
                              CHECKOUT_CLOSE_MIN))
        self._checkout('manual', at=checkout_at, reason=reason)
        self._recompute_credit()
        return True

    # ------------------------------------------------------------------
    # 研討會積分（§8）
    # ------------------------------------------------------------------
    def _credit_status(self):
        """全程判定。順序是刻意的：先看有沒有到，再看遲到，最後才看簽退。"""
        self.ensure_one()
        meeting = self.meeting_id
        if self.state != 'present':
            return 'absent'
        if self.checkin_at and self.checkin_at > meeting.date_begin + _minutes(meeting.checkin_grace_min):
            return 'late'
        if not self.checkout_at:
            return 'no_checkout'
        earliest, latest = self._checkout_window()
        if self.checkout_at < earliest:
            return 'early_leave'
        if self.checkout_at > latest:
            # 越界補登：時間對不上「全程」，不能當成符合
            return 'no_checkout'
        return 'eligible'

    def _recompute_credit(self):
        """重算積分。人工調整過的跳過，否則管理員的更正會被下一次重算蓋掉。"""
        for att in self:
            if att.credit_overridden or att.meeting_id.kind != 'seminar':
                continue
            status = att._credit_status()
            att.with_context(**{GUARD_CREDIT: GUARD}).write({
                'credit_status': status,
                'credit_points': att.meeting_id.credit_points if status == 'eligible' else 0,
            })
        return True

    def action_credit_override(self, status, points, reason):
        """人工調整積分（認可公文、補件等）。之後重算一律跳過這筆。"""
        self.ensure_one()
        self._check_admin()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('人工調整積分必須填寫原因。'))
        before = {'credit_status': self.credit_status, 'credit_points': self.credit_points}
        self.with_context(**{GUARD_CREDIT: GUARD}).write({
            'credit_status': status,
            'credit_points': int(points or 0),
            'credit_note': reason,
            'credit_overridden': True,
        })
        self.env['assoc.audit.log']._log(
            'credit_override', records=self.member_id,
            detail={'meeting_id': self.meeting_id.id, 'before': before,
                    'after': {'credit_status': status, 'credit_points': int(points or 0)}})
        return True

    def button_manual_checkout(self):
        """表單按鈕：用上面填的時間與原因補登簽退。"""
        self.ensure_one()
        if not self.input_checkout_at:
            raise UserError(_('請先填補登簽退時間。'))
        self.action_manual_checkout(self.input_checkout_at, self.input_reason)
        self.write({'input_checkout_at': False, 'input_reason': False})
        return True

    def button_credit_override(self):
        """表單按鈕：用上面填的判定與積分做人工調整。"""
        self.ensure_one()
        if not self.input_credit_status:
            raise UserError(_('請先選擇要調整成哪一種判定。'))
        self.action_credit_override(self.input_credit_status, self.input_credit_points,
                                    self.input_reason)
        self.write({'input_credit_status': False, 'input_credit_points': 0,
                    'input_reason': False})
        return True

    # ------------------------------------------------------------------
    def _desk_info(self):
        self.ensure_one()
        member = self.member_id
        return {
            'attendance_id': self.id,
            'member_id': member.id,
            'member_no': member.member_no,
            'name': member.name,
            'state': self.state,
            'method': self.checkin_method or '',
            'checked_out': bool(self.checkout_at),
            # 沒有照片時台面要顯示「請核對證件」：動態碼防不了即時轉傳，照片是唯一的人工關卡
            'photo': image_data_uri(member.image_128) if member.image_128 else '',
        }
