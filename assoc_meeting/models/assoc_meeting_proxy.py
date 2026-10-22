"""委託出席（人民團體法 §38，計畫 §7）。

兩條硬規定：委託出席不得超過親自出席的 **1/3**，每人只能代理 **1 人**。

三個實作上的取捨：

1. **1/3 在「生效」時判定，不是在「登記」時**。登記時還不知道最後有多少人親自出席，
   而生效當下成立就一直成立——大會沒有簽退，present 只增不減。

2. **判定要序列化**。RR 之下 `SELECT ... FOR UPDATE` 只鎖不改不會 40001 → 兩個報到台
   同時代簽會各自讀到同一組數字（write skew）。所以先真的 `UPDATE meeting.proxy_serial`，
   讓併發者撞 40001 由 `retrying` 重跑（`service/model.py`）。

3. **每人代理 1 人靠先查再擋，唯一索引只當最後防線**。raw SQL 撞 IntegrityError 會讓
   整批回滾而且不重試（`service/model.py:161-176`），FIFO 批次會整個掛掉。

前台送出的委託一律停在 `requested`：人團法要的是「書面委託」，電子委託是否等同
尚待社會局函釋（§14 #1），所以要報到台或管理員勾「已收書面」才生效。
"""

import hmac as hmac_lib

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.assoc_base import tools
from odoo.addons.assoc_base.tools import (GUARD, assert_own_company, check_created,
                                           check_guild_admin, guarded, with_guard)

from .assoc_meeting_attendance import GUARD_CHECKIN

GUARD_PROXY = 'assoc_proxy'
ADMIN_GROUP = 'assoc_base.group_assoc_admin'
# 生效後才佔用受託人的名額；requested 不佔，否則有人可以用大量申請把別人卡住
HOLDING_STATES = ('waiting', 'active')
# 人團法 §38：委託出席不得超過親自出席人數的 1/3
PROXY_RATIO_DIVISOR = 3
# 掃描檔是證據不是狀態：管理員可以直接在表單上傳，不需要經過流程
EVIDENCE_FIELDS = frozenset({'paper_file', 'paper_file_name'})
# 可以讓委託**生效**的會議狀態：報到在開會中仍然繼續（遲到的人照樣簽到），
# 所以代簽也還開著。散會之後就不行——那是回頭改一場已結束的大會。
ACTIVATABLE_MEETING_STATES = ('draft', 'checkin_open', 'in_session')
# 可以**撤回已生效**委託的會議狀態：只到開議之前。
# 法定人數與表決權重是在 `action_start_session` 當下定的（那裡會驗 1/3），
# 開議後還能撤回等於在議程進行中把出席人數抽掉，而系統沒有決議時點的快照。
RELEASABLE_MEETING_STATES = ('draft', 'checkin_open')


class AssocMeetingProxy(models.Model):
    _name = 'assoc.meeting.proxy'
    _description = '委託出席'
    _order = 'meeting_id, requested_at, id'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    meeting_id = fields.Many2one(
        'assoc.meeting', string='大會', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='meeting_id.company_id', store=True, index=True)
    principal_member_id = fields.Many2one(
        'assoc.member', check_company=True, string='委託人', required=True, ondelete='restrict', index=True)
    holder_member_id = fields.Many2one(
        'assoc.member', check_company=True, string='受託人', required=True, ondelete='restrict', index=True)
    purpose = fields.Selection([
        ('attend', '大會出席'),
        ('gift', '禮品代領'),
    ], string='委託事項', required=True, default='attend')
    state = fields.Selection([
        ('requested', '待收書面'),
        ('waiting', '候補'),
        ('active', '已生效'),
        ('superseded', '本人到場'),
        ('cancelled', '已取消'),
        ('rejected', '已退回'),
    ], string='狀態', default='requested', required=True, readonly=True, index=True)
    channel = fields.Selection([
        ('portal', '會員前台'),
        ('desk_paper', '報到台紙本'),
        ('backend', '後台建立'),
    ], string='來源', required=True, default='backend', readonly=True)
    paper_received = fields.Boolean(string='已收書面委託書', readonly=True)
    paper_file = fields.Binary(string='委託書掃描檔', attachment=True,
                               groups='assoc_base.group_assoc_admin')
    paper_file_name = fields.Char(string='檔名')
    requested_at = fields.Datetime(string='登記時間', readonly=True, default=fields.Datetime.now)
    activated_at = fields.Datetime(string='生效時間', readonly=True)
    activated_by_uid = fields.Many2one('res.users', string='生效經手人', readonly=True)
    cancel_reason = fields.Char(string='取消／退回原因', readonly=True)
    # 委託書單號：明碼只在列印那一次回傳，這裡只存**帶伺服器秘密的 HMAC**。
    # 為什麼不是 sha256：亂數那段只有 13 位十進位（約 2^43），而 `proxy_id` 是明碼，
    # 所以無鹽 sha256 的離線搜尋空間就是 10^13——第十三輪 red-team 以 1e10 H/s 估約
    # 1000 秒就回推得出可掃的碼。`activation_nonce_hash` 用 sha256 沒問題是因為
    # 它的 nonce 有 128 bit；這裡沒有，所以要走 `odoo_hmac`（同 `desk_ref`／`pass_token`）。
    # 「重印即作廢」仍然是白送的：覆寫這個值就讓外面那張紙失效。
    # `groups=` 是因為它是「這一筆有沒有發出過可掃的紙」的線索。
    # **列印次數與時間刻意不存成欄位**：它們原本零讀者、只被寫（`ballot_count`
    # 那個裝飾性欄位的形狀），而且沒有 `groups=` 反而把 hash 想遮的線索漏回去。
    # 改寫 `assoc.audit.log` 的 `proxy_form_print`——承辦真的會看那裡，而且它 append-only。
    form_code_hash = fields.Char(string='單號雜湊', readonly=True, copy=False,
                                 groups=ADMIN_GROUP)

    def init(self):
        """互斥靠 DB 的 partial unique index，不靠 Python 約束。

        Python 約束在 REPEATABLE READ 下擋不住併發：兩個交易改的是不同的列，
        各自讀到「還沒有人代理」然後各自寫入（write skew）。
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS assoc_proxy_holder
                ON assoc_meeting_proxy (meeting_id, holder_member_id, purpose)
             WHERE state IN ('waiting', 'active');
            CREATE UNIQUE INDEX IF NOT EXISTS assoc_proxy_principal
                ON assoc_meeting_proxy (meeting_id, principal_member_id, purpose)
             WHERE state IN ('requested', 'waiting', 'active');
            DROP INDEX IF EXISTS assoc_proxy_holder_attend;
            DROP INDEX IF EXISTS assoc_proxy_holder_gift;
        """)

    # ------------------------------------------------------------------
    # 守衛
    # ------------------------------------------------------------------
    def write(self, vals):
        """白名單：狀態與歸屬只能由本模組的方法寫。

        少了這道，報到台（對本模型只有讀權限以外的任何寫入 ACL）可以用 RPC
        把 `channel` 從 portal 改成 desk_paper，書面閘門就等於不存在。

        例外是**掃描檔**：它是證據不是狀態，沒有任何閘門讀它。
        不開這個例外的話，後台表單上的上傳欄位按存檔一定噴錯（等於做了不能用的功能）。
        """
        if not guarded(self.env, GUARD_PROXY):
            if set(vals) - EVIDENCE_FIELDS:
                raise UserError(_('委託書只能由委託流程變更。'))
            self._check_admin()
        return super().write(vals)

    def _check_admin(self):
        check_guild_admin(self)   # 訊息＝預設值，不重複寫一次

    def unlink(self):
        """生效過的委託書不能刪。

        `attendance.proxy_id` 是 `ondelete='set null'`——三種 ondelete 裡唯一
        「破壞看起來像成功」的那種：刪掉委託書，出席列還留在 `proxy` 狀態、
        仍然算進法定人數，卻再也查不到依據，`_release_attendance` 也永遠找不到它。
        """
        if any(proxy.state == 'active' or proxy.activated_at for proxy in self):
            raise UserError(_('生效過的委託書不能刪除（出席是法定人數的依據）。'))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if not guarded(self.env, GUARD_PROXY):
            # 沒有經過流程的 create 只允許管理員，而且一定是後台來源
            if not self.env.user.has_group(ADMIN_GROUP):
                raise AccessError(_('只有公會管理員可以直接建立委託書。'))
            for vals in vals_list:
                vals['channel'] = 'backend'
            # **公會要驗在 `super().create()` 之前，而且要對「大會」驗。**
            # 第十三輪我寫在 create 之後、對 `records` 驗——第十四輪 skeptic 實跑
            # 證明那一行**永遠輪不到執行**：`super().create()` 內部的
            # `_validate_fields` 會先跑 `_check_parties`，它讀 `principal.company_id`，
            # 於是 `assoc.member` 的公會 rule 先丟核心的 AccessError。
            # 靠別人的 rule 順手擋住不算防線（那是這一整輪在消滅的「巧合防線」），
            # 而且錯誤訊息不可預測。改成對 `meeting_id` 驗：這筆委託屬於哪個公會，
            # 問的就是那場大會。
            meetings = self.env['assoc.meeting'].browse(
                [vals.get('meeting_id') for vals in vals_list if vals.get('meeting_id')])
            assert_own_company(meetings.exists(),
                               _('只有公會管理員可以直接建立委託書。'))
        records = super().create(vals_list)
        # **`paper_received` 刻意不放進這個白名單。** 第十三輪 red-team 建議放，
        # 我照做之後 `test_direct_create_is_forced_to_backend_channel` 立刻紅：
        # 後台建檔時管理員說「紙在我手上」是**正當動作**，禁掉是把功能拿走。
        # 它要的保證不是「不准設」，是「設了要有作者」——所以改成下面補軌跡。
        check_created(records, {'state': 'requested', 'activated_at': False,
                                'form_code_hash': False}, GUARD_PROXY)
        # 翻旗標的每一條路都要留下作者（L9）：`_new_proxy` 走 `_mark_paper_received`，
        # 而後台直接 create 帶 `paper_received=True` 繞過那一支，軌跡要在這裡補。
        for record in records:
            if record.paper_received:
                record._log_paper_received()
        return records

    @api.constrains('principal_member_id', 'holder_member_id', 'meeting_id', 'purpose')
    def _check_parties(self):
        for proxy in self:
            principal, holder = proxy.principal_member_id, proxy.holder_member_id
            if principal == holder:
                raise ValidationError(_('不能委託給自己。'))
            if principal.company_id != holder.company_id:
                raise ValidationError(_('委託人與受託人必須屬於同一公會。'))
            if principal.company_id != proxy.meeting_id.company_id:
                raise ValidationError(_('委託人與大會必須屬於同一公會。'))
            if proxy.purpose == 'attend' and proxy.meeting_id.kind != 'assembly':
                raise ValidationError(_('只有會員大會才有委託出席。'))
            # 逐人比對，不要用「筆數 < 2」：委託人與受託人相同時 `principal | holder`
            # 會去重成一筆，那個寫法會用「不在名冊」的理由擋下來，
            # 訊息不對，而且讓上面那道自我委託的檢查看起來可有可無。
            on_roster = self.env['assoc.meeting.attendance'].sudo().search([
                ('meeting_id', '=', proxy.meeting_id.id),
                ('member_id', 'in', (principal | holder).ids)]).member_id
            missing = (principal | holder) - on_roster
            if missing:
                raise ValidationError(_('委託人與受託人都必須在本場的出席名冊內（%s）。',
                                        ', '.join(missing.mapped('member_no'))))

    # ------------------------------------------------------------------
    # 登記
    # ------------------------------------------------------------------
    @api.model
    def _new_proxy(self, meeting, principal, holder, purpose='attend', channel='backend',
                   paper_received=False):
        """建立一張委託書。`channel` 與 `purpose` 只在這裡決定，之後不可改。

        名字不能叫 `_register`：那是 ORM 的保留類別屬性（`BaseModel._register` 是布林），
        覆寫掉會讓呼叫變成 `'bool' object is not callable`。
        """
        values = {
            'meeting_id': meeting.id,
            'principal_member_id': principal.id,
            'holder_member_id': holder.id,
            'purpose': purpose,
            'channel': channel,
            'requested_at': fields.Datetime.now(),
        }
        proxy = with_guard(self.sudo(), GUARD_PROXY).create(values)
        # 哨兵只包 create 這個呼叫本身（§16 通則 2）：回傳帶著哨兵的 recordset 等於
        # 把守衛的鑰匙一起交出去——拿到它的人之後每一次 write 都會通過。
        proxy = proxy.with_env(self.env)
        if paper_received:
            proxy._mark_paper_received()
        return proxy

    def _mark_paper_received(self):
        """翻「已收書面」並留痕。

        **稽核不是裝飾。** 第十三輪 red-team 實跑：對已報到的人打
        `/assoc/desk/<mid>/manual` 會回一個含 `member_id` 的 `already`，
        於是 `desk.py` 照樣鑄出 `desk_ref`——零寫入、零紀錄——再拿那把憑證打
        `/proxy/receive` 就翻得動這個旗標。人不必在場、紙不必存在。
        原本這裡不寫 audit，於是「已收書面」是一個**沒有作者、沒有證據**的布林值，
        而它正是人民團體法 §38 那 1/3 分母的入口。
        擋不住（承辦本來就有這個權限，D6「安全帶不是防線」），但一定要留得下來。
        寫在這支而不是各呼叫端：三條路（報到台、後台按鈕、後台建檔）都經過這裡（L9）。
        """
        self.ensure_one()
        if self.sudo().paper_received:
            return                      # 已經翻過就不要再灌一筆
        self.sudo().with_context(**{GUARD_PROXY: GUARD}).write({'paper_received': True})
        self._log_paper_received()

    def _log_paper_received(self):
        """「已收書面」的軌跡。**三條路共用**：報到台、後台按鈕、後台建檔。"""
        self.ensure_one()
        proxy = self.sudo()
        self.env['assoc.audit.log']._log(
            'proxy_paper_received', records=proxy.principal_member_id,
            company=proxy.company_id,
            detail={'meeting_id': proxy.meeting_id.id, 'proxy_id': proxy.id,
                    'channel': proxy.channel, 'state': proxy.state})

    # ------------------------------------------------------------------
    # 委託書單號（計畫 v14 M11）
    # ------------------------------------------------------------------
    def _issue_form_code(self):
        """鑄一個新的委託書單號，**並讓外面那張舊的失效**。回傳明碼（只此一次）。

        重印要作廢舊的，理由與開通通知單（`action_print_activation`）完全相同：
        同一筆委託在外面同時有兩張可掃的紙，就回答不了「承辦掃的是哪一張」。
        覆寫 hash 就達成作廢，不需要另外一個狀態欄位。
        """
        self.ensure_one()
        code = tools.proxy_form_code(self.id)
        proxy = self.sudo()
        proxy.with_context(**{GUARD_PROXY: GUARD}).write({
            'form_code_hash': tools.proxy_form_hash(self.env, code),
        })
        # 列印次數與時間走稽核，不走欄位（理由見 `form_code_hash` 上方註解）
        self.env['assoc.audit.log']._log(
            'proxy_form_print', records=proxy.principal_member_id,
            company=proxy.company_id,
            detail={'meeting_id': proxy.meeting_id.id, 'proxy_id': proxy.id,
                    'state': proxy.state})
        return code

    def _desk_payload(self):
        """給報到台畫面看的欄位。**刻意不含 `member_id`。**

        `desk.py` 的 `_with_desk_context` 看到回應頂層有 `member_id` 就會鑄
        `desk_ref`，而 `desk_ref(source='scan')` 是禮品領取的「卡被掃過」憑證。
        受託人那一邊用 `holder_member_id` 這個鍵名，委託人那一邊也一樣——
        兩者都不是 `member_id`，所以鑄不出憑證。
        """
        self.ensure_one()
        proxy = self.sudo()
        # 只回畫面真的畫得出來的鍵。`principal_member_id`／`purpose`／`state`
        # 原本沒有任何消費者（前兩者與 `*_label` 重複，第三者同理），
        # 少回一個 member id 就少給翻拍者一個可用的值。
        return {
            'id': proxy.id,
            'principal_no': proxy.principal_member_id.member_no,
            'principal_name': proxy.principal_member_id.name,
            'holder_member_id': proxy.holder_member_id.id,
            'holder_no': proxy.holder_member_id.member_no,
            'holder_name': proxy.holder_member_id.name,
            'purpose_label': dict(self._fields['purpose'].selection)[proxy.purpose],
            'state_label': dict(self._fields['state'].selection)[proxy.state],
            'paper_received': proxy.paper_received,
        }

    def action_print_proxy_form(self):
        """後台列印帶單號的委託書。重印會換碼，外面那張舊的立即失效。

        限公會管理員：委託書上有委託人與受託人的姓名與會員編號，
        而報到台對本模型只有讀取權（他要的是掃碼，不是列印）。

        單號走報表的 `data`（前端是 POST `/report/download`），
        不進網址列也不進 access log——與開通通知單同一條路。
        """
        self.ensure_one()
        self._check_admin()
        if self.state not in ('requested', 'waiting'):
            raise UserError(_('只有「待收書面」或「候補」的委託書需要列印。'))
        if self.env['ir.actions.report'].get_wkhtmltopdf_state() not in ('ok', 'upgrade'):
            raise UserError(_('PDF 產生器目前不可用，請洽系統管理員後再列印。'))
        code = self._issue_form_code()
        return self.env.ref('assoc_meeting.action_report_proxy_form').report_action(
            self, data={'code': code})

    @api.model
    def _by_form_code(self, code):
        """單號 → 委託紀錄。形狀不對、id 不存在、hash 不符一律回空集合。

        **回空集合而不是 raise、也不區分失敗原因**：這個值來自掃碼槍，
        而且不同的失敗原因如果回不同的話，就變成「這個 id 存在嗎」的探測工具
        （比照 `verify_pass_token`「MAC 不符一律 invalid」）。
        """
        proxy_id = tools.proxy_id_from_code(code)
        if not proxy_id:
            return self.browse()
        proxy = self.sudo().browse(proxy_id).exists()
        stored = proxy.form_code_hash if proxy else None
        if not stored or not hmac_lib.compare_digest(stored, tools.proxy_form_hash(self.env, code)):
            return self.browse()
        return proxy

    def action_receive_paper(self):
        """後台勾「已收書面」，並立刻嘗試生效。"""
        self.ensure_one()
        # **不要在這裡自己寫 has_group**：`_check_admin` 同時驗公會，
        # 而這一支正是第十三輪 red-team 打穿的那一支（它當時是內嵌的群組檢查，
        # 沒走 `_check_admin`，於是台北管理員翻得動新北的委託書）。
        self._check_admin()
        self._mark_paper_received()
        return self._try_activate()

    def action_cancel(self, reason=''):
        """取消委託。**只有公會管理員**走得到這裡。

        會員自己取消走前台（`/my/assoc/proxies/<id>/cancel`），那條路由會硬帶
        `principal_member_id` 再呼叫 `_cancel`。

        兩道閘門缺一不可：
        - 權限：這個方法會把出席紀錄退回 `absent`。少了檢查，對本模型只有
          **讀取** ACL 的報到台就能用一行 RPC 作廢任何一張已生效的委託。
        - 會議狀態：開議之後取消，等於在議程進行中把出席人數抽掉。
        """
        self.ensure_one()
        self._check_admin()
        return self._cancel(reason)

    def _cancel(self, reason=''):
        """取消的實作（呼叫端負責權限）。"""
        self.ensure_one()
        proxy = self.sudo()
        if proxy.state == 'active' and proxy.meeting_id.state not in RELEASABLE_MEETING_STATES:
            raise UserError(_('大會已經開議，生效的委託不能再撤回。'))
        if proxy.state == 'active':
            proxy._release_attendance()
        proxy.with_context(**{GUARD_PROXY: GUARD}).write({
            'state': 'cancelled', 'cancel_reason': reason or ''})
        self.env['assoc.audit.log']._log(
            'proxy_cancel', records=proxy.principal_member_id,
            company=proxy.company_id, detail={'meeting_id': proxy.meeting_id.id,
                                              'proxy_id': proxy.id})
        return True

    # ------------------------------------------------------------------
    # 生效（§7）
    # ------------------------------------------------------------------
    def _paper_gate_open(self):
        self.ensure_one()
        return self.channel != 'portal' or self.paper_received

    def _try_activate(self):
        """嘗試讓這張委託書生效。回傳狀態字串，不丟例外（報到台要看得到原因）。"""
        self.ensure_one()
        proxy = self.sudo()
        if proxy.state not in ('requested', 'waiting'):
            return proxy.state
        # 報到有 OPEN_MEETING_STATES 閘，生效也要有：散會之後讓委託生效，
        # 等於回頭改一場已經結束的大會的出席與法定人數
        if proxy.meeting_id.state not in ACTIVATABLE_MEETING_STATES:
            return 'meeting_closed'
        if not proxy._paper_gate_open():
            return 'need_paper'
        if proxy.purpose == 'gift':
            return proxy._activate_gift()
        return proxy._activate_attend()

    def _activate_gift(self):
        """禮品代領不受 1/3 限制，也不動出席紀錄——它只是「誰可以代領」。"""
        self.ensure_one()
        if self._holder_taken():
            return self._reject(_('受託人已代領 1 人'))
        self.env.cr.execute("""
            UPDATE assoc_meeting_proxy
               SET state = 'active', activated_at = (now() AT TIME ZONE 'UTC'),
                   activated_by_uid = %s
             WHERE id = %s AND purpose = 'gift' AND state IN ('requested', 'waiting')
               AND (channel <> 'portal' OR paper_received)
             RETURNING id
        """, [self.env.uid, self.id])
        if not self.env.cr.fetchone():
            return 'failed'
        self.env['assoc.meeting.proxy'].invalidate_model(
            ['state', 'activated_at', 'activated_by_uid'])
        self.env['assoc.audit.log']._log(
            'proxy_activate', records=self.principal_member_id,
            detail={'meeting_id': self.meeting_id.id, 'proxy_id': self.id, 'purpose': 'gift'})
        return 'active'

    def _holder_taken(self):
        """受託人在這場是否已經用掉他的名額。

        人團法 §38 是「每人**只能代理 1 人**」，不是「同時只持有 1 件」：
        生效過就算用掉了。只看當下狀態的話，報到台可以
        「登記→生效→取消→再登記下一位」，同一個人代理任意多人。
        所以 `activated_at` 一旦寫上就永久佔住名額（取消也不釋放）。

        先查再擋，不靠撞唯一索引：raw SQL 的 IntegrityError 會讓整批回滾而且不重試，
        FIFO 批次處理會整個掛掉（`service/model.py:161-176`）。
        """
        self.ensure_one()
        return bool(self.sudo().search_count([
            ('meeting_id', '=', self.meeting_id.id),
            ('holder_member_id', '=', self.holder_member_id.id),
            ('purpose', '=', self.purpose),
            '|', ('state', 'in', HOLDING_STATES), ('activated_at', '!=', False),
            ('id', '!=', self.id),
        ]))

    def _reject(self, reason):
        self.sudo().with_context(**{GUARD_PROXY: GUARD}).write({
            'state': 'rejected', 'cancel_reason': reason})
        return 'rejected'

    def _activate_attend(self):
        """大會出席的生效：序列化 → 驗 1/3 → 寫出席 → 寫委託書。

        整段包在 savepoint 裡：出席列先寫、委託書後寫，中間任何一步失敗都必須
        整筆退回。`raise` 本身**不會**回滾——而呼叫端（報到台 controller）把
        `UserError` 轉成回應之後，交易會照常 commit，半套狀態就留在資料庫裡
        （出席列是 `proxy`、委託書還是 `requested`，而且佔住唯一索引）。
        savepoint 只包這段 SQL；40001 等序列化失敗仍然往外拋給核心 `retrying`。
        """
        self.ensure_one()
        if self._holder_taken():
            return self._reject(_('受託人已代理 1 人'))
        with self.env.cr.savepoint():
            return self._activate_attend_sql()

    def _activate_attend_sql(self):
        meeting, principal, holder = self.meeting_id, self.principal_member_id, self.holder_member_id
        cr = self.env.cr
        self.env.flush_all()

        # 1) 真的改一列來序列化：只 SELECT FOR UPDATE 在 RR 下不會 40001（write skew）
        cr.execute("UPDATE assoc_meeting SET proxy_serial = proxy_serial + 1 WHERE id = %s",
                   [meeting.id])

        # 2) 1/3 上限：加上這一件之後仍要成立
        cr.execute("""
            SELECT count(*) FILTER (WHERE state = 'present'),
                   count(*) FILTER (WHERE state = 'proxy')
              FROM assoc_meeting_attendance
             WHERE meeting_id = %s AND company_id = %s
        """, [meeting.id, meeting.company_id.id])
        present, proxied = cr.fetchone()
        if PROXY_RATIO_DIVISOR * (proxied + 1) > present:
            self.sudo().with_context(**{GUARD_PROXY: GUARD}).write({'state': 'waiting'})
            return 'waiting'

        # 3) 出席紀錄：委託人未到 ∧ 受託人已親自出席，兩個條件都在同一句裡
        cr.execute("""
            UPDATE assoc_meeting_attendance a
               SET state = 'proxy', proxy_id = %s, checkin_method = 'proxy',
                   checkin_by_uid = %s, checkin_at = (now() AT TIME ZONE 'UTC')
             WHERE a.meeting_id = %s AND a.company_id = %s AND a.member_id = %s
               AND a.state = 'absent'
               AND EXISTS (SELECT 1 FROM assoc_meeting_attendance h
                            WHERE h.meeting_id = %s AND h.member_id = %s AND h.state = 'present')
             RETURNING a.id
        """, [self.id, self.env.uid, meeting.id, meeting.company_id.id, principal.id,
              meeting.id, holder.id])
        if not cr.fetchone():
            raise UserError(_('無法代簽：請確認受託人已親自報到、且委託人尚未出席。'))

        # 4) 委託書本身（書面閘門再擋一次：中間有人取消勾選就會是 0 列）
        cr.execute("""
            UPDATE assoc_meeting_proxy
               SET state = 'active', activated_at = (now() AT TIME ZONE 'UTC'),
                   activated_by_uid = %s
             WHERE id = %s AND purpose = 'attend' AND state IN ('requested', 'waiting')
               AND (channel <> 'portal' OR paper_received)
             RETURNING id
        """, [self.env.uid, self.id])
        if not cr.fetchone():
            raise UserError(_('委託書狀態已變更，請重新整理後再試。'))

        self.env['assoc.meeting.attendance'].invalidate_model(
            ['state', 'proxy_id', 'checkin_method', 'checkin_by_uid', 'checkin_at'])
        self.env['assoc.meeting.proxy'].invalidate_model(
            ['state', 'activated_at', 'activated_by_uid'])
        self.env['assoc.audit.log']._log(
            'proxy_activate', records=principal,
            detail={'meeting_id': meeting.id, 'proxy_id': self.id, 'purpose': 'attend',
                    'holder_member_id': holder.id})
        return 'active'

    def _supersede(self):
        """委託人親自到場：退回出席紀錄、標記本人到場、留軌跡。"""
        self.ensure_one()
        self._release_attendance()
        self.sudo().with_context(**{GUARD_PROXY: GUARD}).write({'state': 'superseded'})
        self.env['assoc.audit.log']._log(
            'proxy_cancel', records=self.principal_member_id,
            detail={'meeting_id': self.meeting_id.id, 'proxy_id': self.id,
                    'reason': 'principal_attended'})
        return True

    def _release_attendance(self):
        """委託取消或本人到場：把出席紀錄退回未到（本人到場時由報到流程覆寫成 present）。"""
        self.ensure_one()
        attendance = self.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', self.meeting_id.id),
            ('member_id', '=', self.principal_member_id.id),
            ('proxy_id', '=', self.id), ('state', '=', 'proxy')], limit=1)
        if attendance:
            attendance.with_context(**{GUARD_CHECKIN: GUARD}).write({
                'state': 'absent', 'proxy_id': False, 'checkin_at': False,
                'checkin_method': False, 'checkin_by_uid': False})
        return True
