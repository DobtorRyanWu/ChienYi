# -*- coding: utf-8 -*-

import operator as py_operator

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

# 供 attachment_count 的 search 方法把 domain 運算子翻成 Python 比較
ATTACHMENT_COUNT_OPERATORS = {
    '=': py_operator.eq,
    '!=': py_operator.ne,
    '<': py_operator.lt,
    '<=': py_operator.le,
    '>': py_operator.gt,
    '>=': py_operator.ge,
}


class SupervisionDocument(models.Model):
    """
    應交文件管制表（原「工程文件」，2026-08-20 依定位改名）

    設計特點：
    - 簡潔的文件分類體系
    - 附件歷史記錄（自動保留所有版本）
    - 簡化的狀態流程（草稿/已上傳/已封存）
    """
    _name = 'supervision.document'
    _description = '應交文件管制表'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    active = fields.Boolean(string='啟用', default=True)

    name = fields.Char(
        string='文件名稱', required=True, tracking=True)

    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        required=True, ondelete='cascade', index=True, tracking=True)

    # === 文件分類 ===
    document_category_id = fields.Many2one(
        'supervision.document.category',
        string='文件分類',
        required=True,
        index=True,
        tracking=True,
        help='選擇此文件所屬的分類')

    # 向下相容：保留舊欄位作為關聯欄位
    document_type = fields.Char(
        string='舊文件類型代碼',
        related='document_category_id.code',
        store=False,
        readonly=True,
        help='僅供系統內部使用')

    # === 文件編號 ===
    document_no = fields.Char(
        string='文件編號', copy=False, index=True,
        help='系統自動產生的文件編號')

    # === 附件管理（支援歷史記錄） ===
    # 上傳新附件的可寫欄位
    upload_attachment_ids = fields.Many2many(
        'ir.attachment',
        'supervision_document_upload_attachment_rel',
        'document_id', 'attachment_id',
        string='上傳附件',
        help='點擊此處上傳新的文件附件')
    
    attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='所有附件',
        help='包含當前附件與歷史附件')

    current_attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='當前附件',
        help='目前有效的附件檔案')

    history_attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachments',
        string='歷史附件',
        help='已被替換的舊版本附件')

    # 2026-08-20：這兩欄原本宣告 store=True，但 _compute_attachments 是靠
    # search(res_model/res_id) 找附件，**沒有任何 ORM 追得到的相依**，
    # 所以既沒有 @api.depends 也不可能有——結果是存了一個永遠不會自動更新的值
    # （實測 doc 2/3/12 的 attachment_count 是 NULL，從未算過）。
    # 而且同一個 compute 同時餵儲存與非儲存欄位，Odoo 18 會發出
    # 「inconsistent 'store' for computed fields」警告。
    # 改為非儲存：每次讀取都重算，永遠正確，也不再需要 _trigger_document_recompute
    # 那套手動補算的機制。
    # 代價：非儲存欄位不能排序、也不能直接放進 domain，所以 attachment_count
    # 另外提供 search 方法給「有附件」篩選用。
    attachment_count = fields.Integer(
        string='當前附件數', compute='_compute_attachments',
        search='_search_attachment_count')

    history_count = fields.Integer(
        string='歷史附件數', compute='_compute_attachments')

    def _search_attachment_count(self, operator, value):
        """讓「有附件」這類篩選在非儲存欄位上仍可用。

        不能直接 self.search()——那會再次命中本欄位造成無窮遞迴，
        所以改成先 group by 附件的 res_id 算出每份文件的當前附件數，
        再把比較結果翻譯成 id in / not in。
        """
        compare = ATTACHMENT_COUNT_OPERATORS.get(operator)
        if compare is None or not isinstance(value, (int, float)):
            raise UserError('「當前附件數」只支援數值比較。')

        grouped = self.env['ir.attachment']._read_group(
            [('res_model', '=', self._name),
             ('res_id', '!=', 0),
             ('is_current_version', '=', True)],
            ['res_id'], ['__count'])
        counts = {res_id: count for res_id, count in grouped}
        matched = [doc_id for doc_id, count in counts.items() if compare(count, value)]
        if compare(0, value):
            # 一個附件都沒有的文件也符合條件——它們不在 counts 裡
            return ['|', ('id', 'in', matched), ('id', 'not in', list(counts))]
        return [('id', 'in', matched)]

    def _compute_attachments(self):
        """計算附件相關欄位"""
        Attachment = self.env['ir.attachment']
        for doc in self:
            if doc.id:
                # 取得所有附件
                all_attachments = Attachment.search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', doc.id)
                ])
                
                # 分類當前和歷史附件
                current = all_attachments.filtered(lambda a: a.is_current_version)
                history = all_attachments - current
                
                doc.attachment_ids = all_attachments
                doc.current_attachment_ids = current
                doc.history_attachment_ids = history
                doc.attachment_count = len(current)
                doc.history_count = len(history)
            else:
                doc.attachment_ids = False
                doc.current_attachment_ids = False
                doc.history_attachment_ids = False
                doc.attachment_count = 0
                doc.history_count = 0

    # === 公司關聯 ===
    company_id = fields.Many2one(
        'res.company', string='所屬公司',
        default=lambda self: self.env.company,
        tracking=True,
        help='此文件所屬的公司')

    # === 上傳資訊 ===
    uploader_id = fields.Many2one(
        'res.users', string='上傳者',
        default=lambda self: self.env.uid,
        tracking=True,
        readonly=True)

    upload_date = fields.Datetime(
        string='上傳時間',
        default=fields.Datetime.now,
        tracking=True,
        readonly=True)

    # === 狀態管理（簡化版） ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('uploaded', '已上傳'),
        ('archived', '已封存'),
    ], string='狀態', default='draft', tracking=True, index=True,
       help='草稿：尚未上傳附件；已上傳：已有附件可用；已封存：不再使用')

    # === 到期日提醒 ===
    due_date = fields.Date(
        string='應上傳日期',
        tracking=True,
        help='文件應上傳的期限日期')

    is_overdue = fields.Boolean(
        string='已逾期',
        compute='_compute_is_overdue', store=True)

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for doc in self:
            if doc.due_date and doc.state == 'draft':
                doc.is_overdue = today > doc.due_date
            else:
                doc.is_overdue = False

    # === 備註 ===
    notes = fields.Html(string='備註說明', tracking=True)

    # === 計算欄位：最後更新資訊 ===
    last_update_date = fields.Datetime(
        string='最後更新',
        compute='_compute_last_update')

    last_update_user_id = fields.Many2one(
        'res.users', string='最後更新者',
        compute='_compute_last_update')

    def _compute_last_update(self):
        """計算最後更新資訊"""
        Attachment = self.env['ir.attachment']
        for doc in self:
            if doc.id:
                # 取得最新的附件
                latest = Attachment.search([
                    ('res_model', '=', self._name),
                    ('res_id', '=', doc.id),
                    ('is_current_version', '=', True),
                ], order='create_date desc', limit=1)
                
                if latest:
                    doc.last_update_date = latest.create_date
                    doc.last_update_user_id = latest.create_uid
                else:
                    doc.last_update_date = doc.create_date
                    doc.last_update_user_id = doc.create_uid
            else:
                doc.last_update_date = False
                doc.last_update_user_id = False

    # === 狀態動作 ===
    def action_upload(self):
        """標記為已上傳"""
        for doc in self:
            if not doc.current_attachment_ids:
                raise ValidationError('請先上傳至少一個附件檔案')
            doc.state = 'uploaded'

    def action_archive(self):
        """封存文件"""
        for doc in self:
            doc.state = 'archived'
            doc.active = False

    def action_unarchive(self):
        """取消封存"""
        for doc in self:
            doc.state = 'uploaded' if doc.current_attachment_ids else 'draft'
            doc.active = True

    def action_reset_draft(self):
        """重設為草稿"""
        for doc in self:
            doc.state = 'draft'

    # === 附件管理動作 ===
    def action_view_current_attachments(self):
        """查看當前附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '當前附件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.current_attachment_ids.ids)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
                'default_is_current_version': True,
            },
        }

    def action_view_history_attachments(self):
        """查看歷史附件"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '歷史附件',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.history_attachment_ids.ids)],
            'context': {'create': False},
        }

    def action_replace_attachment(self):
        """替換附件（將當前附件移至歷史）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '替換附件',
            'res_model': 'document.replace.attachment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
            },
        }

    # === 附件歸位 ===
    def _document_folder(self):
        """本文件的附件放進哪個資料夾：依文件分類在該工程的資料夾樹上定位。

        supervision.document **刻意不掛** supervision.attachment.mixin
        （該模型的定位還沒定案，掛上去會連帶改掉 create/write 行為），
        所以直接呼叫 supervision.folder 上的共用建樹方法，邏輯仍只有一份。

        subpath 傳 []：附件直接放在分類資料夾裡，不替每份文件各開一個子資料夾
        —— 一份文件一個資料夾只會把樹打碎。
        """
        self.ensure_one()
        if not self.project_id or not self.document_category_id:
            return self.env['supervision.folder']
        return self.env['supervision.folder'].sudo()._get_or_create_for_category(
            self.project_id, self.document_category_id, subpath=[])

    def _sync_upload_attachments(self):
        """把 upload_attachment_ids 裡的附件補上來源與歸類資訊。

        為什麼需要：`many2many_binary` widget 在記錄尚未儲存時上傳，送出的是
        `res_id: 0`。走 write 的路徑原本有補正，**走 create 的完全沒有**——
        於是「新增文件→上傳附件→存檔」產生的附件 res_id 永遠是 0，
        `_compute_attachments()` 用 res_model/res_id 找不到它們，
        按「標記為已上傳」就會說「請先上傳至少一個附件檔案」。

        歸類欄位沿用全系統一致的「已有值不動」原則：使用者手動把檔案搬去
        別的資料夾或改過分類之後，再存一次文件不會被蓋回去。
        """
        for doc in self:
            attachments = doc.upload_attachment_ids
            if not attachments:
                continue
            folder = (doc._document_folder()
                      if any(not a.folder_id for a in attachments)
                      else self.env['supervision.folder'])
            for attachment in attachments.sudo():
                vals = {}
                if attachment.res_model != doc._name or attachment.res_id != doc.id:
                    vals['res_model'] = doc._name
                    vals['res_id'] = doc.id
                    # 只有「剛掛上這份文件」時才設為當前版本，
                    # 免得把已被替換的歷史版本又復活
                    vals['is_current_version'] = True
                if doc.project_id and not attachment.supervision_project_id:
                    vals['supervision_project_id'] = doc.project_id.id
                if doc.document_category_id and not attachment.document_category_id:
                    vals['document_category_id'] = doc.document_category_id.id
                if folder and not attachment.folder_id:
                    vals['folder_id'] = folder.id
                if vals:
                    attachment.write(vals)

        # 附件相關的計算欄位是靠 search(res_model/res_id) 算的，**沒有任何
        # ORM 追得到的相依**，所以剛剛改了附件並不會讓它們失效。
        # 不手動清快取的話：create() 期間先算過一次得到 0，接著這裡才把 res_id
        # 補上，前端存檔後在同一個 request 裡重讀，拿到的仍是那個 0——
        # 使用者馬上按「標記為已上傳」就會被擋，跟修之前一模一樣。
        self.invalidate_recordset([
            'attachment_ids', 'current_attachment_ids', 'history_attachment_ids',
            'attachment_count', 'history_count',
            'last_update_date', 'last_update_user_id',
        ])

    # === CRUD 覆寫 ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # 自動產生文件編號
            if not vals.get('document_no'):
                vals['document_no'] = self.env['ir.sequence'].next_by_code(
                    'supervision.document') or '/'

            # 設定上傳者和上傳時間
            if not vals.get('uploader_id'):
                vals['uploader_id'] = self.env.uid
            if not vals.get('upload_date'):
                vals['upload_date'] = fields.Datetime.now()

        documents = super().create(vals_list)
        # 必須在 super() 之後：此時才有 doc.id 可以寫進附件的 res_id
        documents._sync_upload_attachments()
        documents._auto_mark_uploaded()
        return documents

    def _auto_mark_uploaded(self):
        """草稿一旦有了當前附件就視為「已上傳」。

        2026-08-20：原本只有 write 會這樣做，create 不會（因為 create 根本沒在
        處理附件）。修好 create 之後這個不一致就浮出來——同樣是「上傳附件並存檔」，
        新增時停在草稿、編輯時卻自動轉。使用者拍板統一成「兩邊都自動轉」，
        「標記為已上傳」按鈕退居備用。
        """
        for doc in self:
            if doc.state == 'draft' and doc.current_attachment_ids:
                doc.state = 'uploaded'

    def write(self, vals):
        # 2026-08-20：原本這裡會 vals.pop('upload_attachment_ids')「避免寫入資料庫」，
        # 結果是存檔後「上傳附件」欄位變空白，而且 construction_portal 前台
        # （只認 upload_attachment_ids，見 portal.py:130）跟著看不到檔案。
        # 現在讓 M2M 照常寫入，補正 res_id 的工作改由 _sync_upload_attachments 做。
        result = super().write(vals)

        if 'upload_attachment_ids' in vals:
            self._sync_upload_attachments()

        self._auto_mark_uploaded()
        return result

    def unlink(self):
        for doc in self:
            if doc.state == 'uploaded':
                raise UserError('已上傳的文件無法刪除，請先封存')
        return super().unlink()

    # Odoo 17 起 name_get() 已移除，改用 _compute_display_name()。
    # 原本這裡寫的是 name_get，等於從未被呼叫、文件編號一直沒顯示出來。
    @api.depends('document_no', 'name')
    def _compute_display_name(self):
        for doc in self:
            doc.display_name = (
                f'[{doc.document_no}] {doc.name}' if doc.document_no else doc.name)

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', ('document_no', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)


class IrAttachment(models.Model):
    """
    擴展附件模型，支援版本標記與工程歸類
    """
    _inherit = 'ir.attachment'

    # === 工程歸類（附件總覽用）===
    # 系統各處（施工日誌、缺失、送審、估驗、檢試驗…）上傳的附件，過去只存在
    # 各自單據的 Many2many 裡，彼此無關聯，「應交文件管制表」也看不到。
    # 這兩欄由 supervision.attachment.mixin 在來源單據儲存時自動補上，
    # 讓所有附件都能在「檔案管理 > 文件管理 > 全部工程附件」集中查找與歸類。
    # 沿用 ir.attachment 本身（res_model/res_id 已記錄來源），不另建資料表。
    supervision_project_id = fields.Many2one(
        'project.project',
        string='所屬工程',
        index=True,
        ondelete='cascade',
        help='此附件所屬的工程案件，由來源單據自動帶入')

    document_category_id = fields.Many2one(
        'supervision.document.category',
        string='文件分類',
        index=True,
        help='此附件的文件分類，由來源單據自動帶入預設值，可手動調整')

    # === 檔案位置（與 document_category_id 正交）===
    # document_category_id 回答「這是什麼文件」（全公司通用語意，供跨案檢索）
    # folder_id           回答「這個檔案放在哪」（per-project 實際存放結構）
    # 真實資料裡同一個資料夾常含多種分類的文件，兩者不可互相取代。
    folder_id = fields.Many2one(
        'supervision.folder',
        string='資料夾',
        index=True,
        ondelete='set null',
        help='此檔案在工程資料夾樹中的位置')

    folder_path = fields.Char(
        string='資料夾路徑',
        related='folder_id.complete_name',
        store=False,
        readonly=True,
        help='供清單顯示')

    @api.constrains('folder_id', 'supervision_project_id')
    def _check_folder_project_match(self):
        """資料夾是 per-project 的，不可把 A 案的檔案掛到 B 案的資料夾"""
        for attachment in self:
            if attachment.folder_id and attachment.supervision_project_id \
                    and attachment.folder_id.project_id != attachment.supervision_project_id:
                raise ValidationError(
                    '檔案「%s」的資料夾屬於不同的工程案件。' % attachment.name)

    is_current_version = fields.Boolean(
        string='當前版本',
        default=True,
        help='標記此附件是否為當前有效版本')

    replaced_date = fields.Datetime(
        string='替換時間',
        help='此附件被替換為歷史版本的時間')

    replaced_by_id = fields.Many2one(
        'res.users', string='替換者',
        help='將此附件替換的使用者')

    version_note = fields.Char(
        string='版本備註',
        help='此版本的說明或變更記錄')

    def action_open_attachment_source(self):
        """開啟這個附件的來源單據（供「全部工程附件」清單跳轉用）"""
        self.ensure_one()
        if not self.res_model or not self.res_id:
            raise UserError('此附件沒有記錄來源單據。')
        if self.res_model not in self.env:
            raise UserError('來源模型「%s」不存在，可能所屬模組已移除。' % self.res_model)
        return {
            'type': 'ir.actions.act_window',
            'name': self.res_name or self.name,
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_restore_as_current(self):
        """將歷史附件恢復為當前版本"""
        for attachment in self:
            if attachment.is_current_version:
                raise UserError('此附件已經是當前版本')
            
            # 將目前的當前版本改為歷史
            current_attachments = self.search([
                ('res_model', '=', attachment.res_model),
                ('res_id', '=', attachment.res_id),
                ('is_current_version', '=', True),
            ])
            current_attachments.write({
                'is_current_version': False,
                'replaced_date': fields.Datetime.now(),
                'replaced_by_id': self.env.uid,
            })
            
            # 恢復此附件為當前版本
            attachment.write({
                'is_current_version': True,
                'replaced_date': False,
                'replaced_by_id': False,
            })
    
    # 2026-08-20：這裡原本覆寫 create / write / unlink，只為了手動補算
    # supervision.document 的 attachment_count / history_count（那兩欄當時是
    # store=True 卻沒有任何 @api.depends）。那兩欄已改為非儲存、讀取時即時計算，
    # 這三個覆寫連同 _trigger_document_recompute 就成了純粹的死重量——
    # 而且它掛在**全系統每一次 ir.attachment 寫入**上。一併移除。
    #
    # 順帶修掉原本 _trigger_document_recompute 的判斷式 `and attachment.res_id`：
    # 走 create 上傳的附件 res_id 是 0，falsy，永遠被跳過，補算機制對
    # 最需要它的那批附件完全沒作用。
