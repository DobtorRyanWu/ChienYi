"""禮品造冊匯出與還原（計畫 §2.4、§9、P17）。

現金與宜睿禮券不在現場發，要出一份名單交出去。名單一旦交出去就當成
「已經發了」——所以匯出會把權利列標成 `exported`，同一批重下載給**同一個檔**
（存檔在附件裡，不重新產生），要重來只能走 `action_revert`（留軌跡）。

欄位用常數表而不是後台可設定（P17）：宜睿的正式範本目前拿不到（§14 #6），
拿到時本來就要開發者核對一次，可設定化只是把錯誤面放大。
"""

import base64
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.assoc_base import tools_export
from odoo.addons.assoc_base.tools import GUARD, check_guild_admin, guarded, with_guard

from .assoc_gift import GUARD_GIFT

GUARD_GIFT_EXPORT = 'assoc_gift_export'
ADMIN_GROUP = 'assoc_base.group_assoc_admin'

# 現金造冊：公會自己用的印領清冊
CASH_COLUMNS = (
    ('會員編號', lambda row: row['member_no'], 'text'),
    ('姓名', lambda row: row['name'], 'text'),
    ('品項', lambda row: row['item'], 'text'),
    ('單價', lambda row: row['amount'], 'int'),
    ('數量', lambda row: row['qty'], 'int'),
    # 印領清冊上的金額要是**實付**：只印單價的話，qty>1 的品項會少發而且看不出來
    ('金額', lambda row: row['total'], 'int'),
    ('備註', lambda row: row['note'], 'text'),
)

# 宜睿禮券：欄位依對方範本 (H)，拿到正式格式改這張表
EDENRED_COLUMNS = (
    ('姓名', lambda row: row['name'], 'text'),
    ('手機', lambda row: row['mobile'], 'text'),
    ('Email', lambda row: row['email'], 'text'),
    ('面額', lambda row: row['amount'], 'int'),
    ('數量', lambda row: row['qty'], 'int'),
    ('備註', lambda row: row['note'], 'text'),
)

KINDS = {'cash': CASH_COLUMNS, 'edenred': EDENRED_COLUMNS}
FILE_TYPES = ('xlsx', 'csv')
# 發放方式 → 匯出種類
DELIVERY_KIND = {'cash_list': 'cash', 'edenred': 'edenred'}


class AssocGiftExport(models.Model):
    _name = 'assoc.gift.export'
    _description = '禮品造冊批次'
    _order = 'id desc'

    campaign_id = fields.Many2one(
        'assoc.gift.campaign', string='活動', required=True, ondelete='restrict', index=True)
    item_id = fields.Many2one(
        'assoc.gift.item', string='品項', required=True, ondelete='restrict', index=True)
    # related store：create 時不要傳值
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    kind = fields.Selection([('cash', '現金造冊'), ('edenred', '宜睿禮券')],
                            string='種類', required=True, readonly=True)
    file = fields.Binary(string='名單檔', readonly=True, attachment=True,
                         groups=ADMIN_GROUP)
    file_name = fields.Char(string='檔名', readonly=True)
    row_count = fields.Integer(string='筆數', readonly=True)
    exception_count = fields.Integer(
        string='例外筆數', readonly=True,
        help='缺手機與 Email 而沒有匯出的人數（宜睿需要聯絡資料才發得出去）。')
    exception_note = fields.Text(string='例外清單', readonly=True)
    sha256 = fields.Char(string='檔案指紋', readonly=True)
    state = fields.Selection([('done', '已匯出'), ('reverted', '已還原')],
                             string='狀態', default='done', required=True, readonly=True)
    revert_reason = fields.Char(string='還原原因', readonly=True)
    entitlement_ids = fields.One2many(
        'assoc.gift.entitlement', 'export_id', string='這批的權利')
    # 承辦的暫存輸入（不用 wizard，本專案慣例）：還原按鈕讀它
    revert_input = fields.Char(string='還原原因（輸入）')

    # ------------------------------------------------------------------
    # 守衛：除了匯出與還原這兩個動作，一律不可寫、不可刪
    # ------------------------------------------------------------------
    def write(self, vals):
        # `revert_input` 是承辦的暫存輸入（不用 wizard，本專案慣例），不影響任何判定：
        # 不放行的話，表單上填完原因按「還原」時 web client 會先存檔，
        # 那個 write 就被擋下來——按鈕永遠按不動（M8 的 `void_input` 同一個形狀）。
        if set(vals) - {'revert_input'} and not guarded(self.env, GUARD_GIFT_EXPORT):
            raise AccessError(_('造冊批次只能由匯出或還原動作變更。'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not guarded(self.env, GUARD_GIFT_EXPORT):
            raise AccessError(_('造冊批次只能由匯出動作建立。'))
        return super().create(vals_list)

    def unlink(self):
        # 批次是「已經交出去的證據」，留著才對得上帳；要作廢請用還原
        raise UserError(_('造冊批次不能刪除；要作廢請用「還原」（會留軌跡）。'))

    # ------------------------------------------------------------------
    def _check_admin(self):
        """**不可以是 `@api.model`。** 掛上去之後 `self` 是空 recordset，
        `assert_own_company` 的迴圈跑零圈＝公會那一半恆真（第十四輪 skeptic
        與 simplifier 各自獨立指到這裡）。造冊那條路的公會在 `item` 上，
        所以 `action_export` 直接對 `item` 驗，不走這支。
        """
        check_guild_admin(self, _('只有公會管理員可以造冊與還原。'))

    @api.model
    def _rows_for(self, item, entitlements, kind):
        """把權利列轉成匯出用的 dict，並分出「缺聯絡資料」的例外。

        宜睿是寄給本人的，沒有手機也沒有 Email 就寄不出去——
        這些人**不匯出**、列進例外清單交回辦公室補資料，
        而不是丟一列空白進去讓對方去猜。
        """
        rows, exceptions, exported = [], [], []
        for row in entitlements:
            member = row.member_id.sudo()
            mobile, email = member.mobile or '', member.email or ''
            base = {
                'member_no': member.member_no or '',
                'name': member.name or '',
                'item': item.name,
                'amount': item.unit_value,
                'qty': item.qty,
                'total': item.unit_value * item.qty,
                'mobile': mobile,
                'email': email,
                'note': '',
            }
            if kind == 'edenred' and not (mobile or email):
                exceptions.append('%s %s（無手機與 Email）' % (base['member_no'], base['name']))
                continue
            rows.append(base)
            exported.append(row.id)
        # 「誰進了名單」只能有一份判斷：另外再算一次遲早會與這裡漂移，
        # 而漂移的後果是有人被標成已造冊卻不在檔案裡（等於漏發）
        return rows, exceptions, exported

    @api.model
    def action_export(self, item, file_type='xlsx'):  # noqa: 這支的 self 是空的
        """把一個品項還沒造冊的權利列匯出成名單。

        只收 `pending`：已經領走或已經造冊過的不會重複出現在名單裡。
        """
        # 對 `item` 驗、不對 `self` 驗：這支是 `@api.model`，`self` 是空 recordset，
        # 公會在 `item` 上（第十四輪抗辯：原本那道公會檢查跑零圈＝恆真）。
        # **`with_env(self.env)` 不可省**：`item` 可能是呼叫端用別的 env（甚至 sudo）
        # browse 出來的，而守衛問的是「**現在這個呼叫者**是誰、看得到哪些公會」。
        # 少了它，既有的 `test_staff_cannot_export` 立刻紅——那正是它守住的事。
        check_guild_admin(item.with_env(self.env),
                          _('只有公會管理員可以造冊與還原。'))
        if file_type not in FILE_TYPES:
            # 不白名單的話，檔名會照抄使用者字串、下載路由再從副檔名推 Content-Type，
            # 結果是「xlsx 的內容、.CSV 的檔名、octet-stream 的型別」
            raise UserError(_('不支援的檔案格式。'))
        kind = DELIVERY_KIND.get(item.delivery)
        if not kind:
            raise UserError(_('「%s」是現場領取的品項，不需要造冊。', item.name))
        entitlements = self.env['assoc.gift.entitlement'].sudo().search([
            ('item_id', '=', item.id), ('state', '=', 'pending'),
        ], order='member_no, id')
        campaign = item.campaign_id
        if campaign._needs_attendance():
            # **造冊也要看出席**。名單是以大會「名冊」建的（全體會員），
            # 出席是在領取當下才判斷的——現場領取那條路有這道檢查，
            # 造冊這條路沒有的話，發放對象是「大會出席者」的現金清冊
            # 會把沒到場的人整批列進去（錢真的會發出去）。
            attended = campaign._attended_member_ids()
            absent = entitlements.filtered(lambda row: row.member_id.id not in attended)
            entitlements -= absent
        if not entitlements:
            raise UserError(_('這個品項沒有待造冊的名單（發放對象是出席者時，'
                              '只有已報到的人會進名單）。'))
        rows, exceptions, exported_ids = self._rows_for(item, entitlements, kind)
        if not rows:
            raise UserError(_('這個品項的名單全部缺聯絡資料，請先補齊再造冊。'))
        content = tools_export.write_rows(KINDS[kind], rows, file_type)
        name = '%s-%s.%s' % (item.campaign_id.name, item.name, file_type)
        export = with_guard(self.sudo(), GUARD_GIFT_EXPORT).create({
            'campaign_id': item.campaign_id.id,
            'item_id': item.id,
            'kind': kind,
            'file': base64.b64encode(content),
            'file_name': name,
            'row_count': len(rows),
            'exception_count': len(exceptions),
            'exception_note': '\n'.join(exceptions) or False,
            'sha256': hashlib.sha256(content).hexdigest(),
        })
        self.env['assoc.gift.entitlement'].sudo().browse(exported_ids).with_context(
            **{GUARD_GIFT: GUARD}).write({'state': 'exported', 'export_id': export.id})
        self.env['assoc.audit.log']._log(
            'gift_export', records=self.env['assoc.gift.entitlement'].browse(exported_ids)
            .member_id, company=item.company_id,
            detail={'export_id': export.id, 'item': item.name, 'kind': kind,
                    'rows': len(rows), 'exceptions': len(exceptions),
                    'sha256': export.sha256})
        # **把哨兵從回傳值上拿掉**：`with_context()` 是疊加不是取代，
        # 直接回傳 `export` 的話，呼叫端經由這個 handle 做的任何寫入
        # 都會帶著哨兵繞過守衛（M7 的 `_new_proxy` 踩過同一個坑）。
        return export.with_env(self.env)

    def action_revert(self, reason=None):
        """還原：這批的權利列退回未造冊，可以重新造冊。

        原檔留著（附件不刪）——已經交出去的那一份是事實，
        重造會產生**新的批次**，兩份都在，人工核對時看得到。
        """
        self.ensure_one()
        self._check_admin()
        reason = (reason if reason is not None else self.revert_input) or ''
        reason = reason.strip()
        if not reason:
            raise UserError(_('還原必須填寫原因。'))
        if self.state != 'done':
            raise UserError(_('只有已匯出的批次可以還原。'))
        rows = self.entitlement_ids
        # ACL 只給 admin「可讀可建」，寫入一律走這裡的 sudo＋哨兵：
        # 批次是「已經交出去的證據」，唯一該動它的就是這個動作。
        rows.sudo().with_context(**{GUARD_GIFT: GUARD}).write(
            {'state': 'pending', 'export_id': False})
        self.sudo().with_context(**{GUARD_GIFT_EXPORT: GUARD}).write(
            {'state': 'reverted', 'revert_reason': reason})
        self.env['assoc.audit.log']._log(
            'gift_revert', records=rows.member_id, company=self.company_id,
            detail={'export_id': self.id, 'reason': reason, 'rows': len(rows)})
        return True

    def button_download(self):
        """下載走有稽核的路由，不直接給 binary 欄位。

        表單上直接放 binary 欄位的話，web client 會走 `/web/content`——
        那條路不會寫軌跡，而「誰把這份含姓名手機的名單抓走了」正是要記的事。
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/assoc/gift/export/%s/download' % self.id,
            'target': 'self',
        }

    def button_revert(self):
        self.ensure_one()
        return self.action_revert()
