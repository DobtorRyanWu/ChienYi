# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SupervisionFolder(models.Model):
    """工程檔案資料夾

    定位：回答「這個檔案放在哪」。與 supervision.document.category（回答
    「這是什麼文件」）是兩個正交維度，不可互相取代——真實資料裡同一個
    資料夾常含多種分類的文件（例：19_工程結案資料 底下同時有驗收派驗
    文件、竣工圖審查表、結案用公文）。

    範圍：per-project。每個工程案件各自一棵樹，A 案的資料夾與 B 案無關，
    因此可照原始 Windows 結構建到任意深度而不污染全域分類樹。
    """
    _name = 'supervision.folder'
    _description = '工程檔案資料夾'
    _order = 'complete_name'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'complete_name'

    # === 基本 ===
    name = fields.Char(string='資料夾名稱', required=True, index=True)

    complete_name = fields.Char(
        string='完整路徑', compute='_compute_complete_name',
        store=True, recursive=True, index=True,
        help='含所有上層的完整路徑，供顯示、搜尋與匯入比對')

    # 清單用的縮排名稱。complete_name 直接當主欄時，層一深就變成
    # 「11-工程資料 / 01-契約及圖說 / 資料夾第一層 / 資料夾第二層 / …」——
    # 前綴一直重複、超寬被截斷，反而看不出結構。
    # 清單預設就以 complete_name 排序（深度優先），所以只要把層級換成縮排，
    # 同一份資料就讀得像一棵樹。
    tree_name = fields.Char(
        string='資料夾', compute='_compute_tree_name', store=True,
        help='依層級縮排的資料夾名稱。完整路徑請開「完整路徑」欄位或進入表單檢視')

    project_id = fields.Many2one(
        'project.project', string='所屬工程',
        required=True, ondelete='cascade', index=True)

    parent_id = fields.Many2one(
        'supervision.folder', string='上層資料夾',
        index=True, ondelete='restrict',
        help='留空代表這是該工程的第一層資料夾')

    parent_path = fields.Char(index=True, unaccent=False)

    child_ids = fields.One2many(
        'supervision.folder', 'parent_id', string='子資料夾')

    sequence = fields.Integer(string='排序', default=10)
    active = fields.Boolean(string='啟用', default=True)
    notes = fields.Text(string='備註')

    company_id = fields.Many2one(
        'res.company', string='所屬公司',
        related='project_id.company_id', store=True, readonly=True)

    # === 與分類的對應（開案產生標準資料夾時填入）===
    source_category_id = fields.Many2one(
        'supervision.document.category', string='對應文件分類',
        index=True, ondelete='set null',
        help='本資料夾由哪個文件分類產生。丟進此資料夾的檔案會自動帶上這個分類')

    # === 自動建立來源（附件自動歸位時填入）===
    source_res_model = fields.Char(
        string='來源模型', index=True, readonly=True, copy=False,
        help='此資料夾由哪個業務單據自動建立，手動建立則為空')

    source_res_id = fields.Integer(
        string='來源記錄 ID', index=True, readonly=True, copy=False)

    is_auto = fields.Boolean(
        string='系統自動建立', compute='_compute_is_auto', store=True,
        help='自動建立的資料夾不建議改名或刪除，否則下次上傳會再生一個')

    # === 匯入稽核 ===
    import_source_path = fields.Char(
        string='匯入來源路徑', readonly=True, copy=False,
        help='由既有資料匯入時記錄的原始檔案系統路徑，僅供稽核追溯')

    # === 檔案 ===
    attachment_ids = fields.One2many(
        'ir.attachment', 'folder_id', string='檔案')

    # 本資料夾及所有下層的檔案。One2many 做不到 child_of，所以用非儲存 Many2many。
    # 用途：在資料夾表單上一次看完整棵子樹的檔案（搭配清單上的「資料夾路徑」欄，
    # 等同把樹攤平），不必逐層點進去。
    all_attachment_ids = fields.Many2many(
        'ir.attachment', string='所有檔案（含子層）',
        compute='_compute_all_attachment_ids')

    attachment_count = fields.Integer(string='檔案數', compute='_compute_counts')
    total_count = fields.Integer(
        string='含子資料夾檔案數', compute='_compute_counts',
        help='本資料夾及其所有下層資料夾的檔案總數')
    child_count = fields.Integer(string='子資料夾數', compute='_compute_counts')

    # -------------------------------------------------------------------
    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for folder in self:
            if folder.parent_id:
                folder.complete_name = f'{folder.parent_id.complete_name} / {folder.name}'
            else:
                folder.complete_name = folder.name or ''

    @api.depends_context('hierarchical_naming')
    def _compute_display_name(self):
        """一般情境顯示完整路徑（_rec_name = complete_name），
        但左側樹狀側欄只顯示自己的名稱。

        searchpanel 的節點本來就已經巢狀排列，再帶完整路徑等於前綴重複兩次，
        而側欄很窄一定被截斷。Odoo 為此預留了 hierarchical_naming context：
        web/models/models.py 的 search_panel_select_range 會用
        `.with_context(hierarchical_naming=False)` 取 comodel 的 display_name。
        product.category 與 hr.department 都是這個寫法。
        """
        if self.env.context.get('hierarchical_naming', True):
            return super()._compute_display_name()
        for folder in self:
            folder.display_name = folder.name

    def _inherited_category(self):
        """沿著資料夾往上找第一個有 source_category_id 的節點。

        這讓「附加子資料夾」（本身沒有分類，例如通報單底下的「通報單掃描」）
        以及使用者手建的下層資料夾，都能沿用上層的文件分類。
        """
        self.ensure_one()
        node = self
        while node:
            if node.source_category_id:
                return node.source_category_id
            node = node.parent_id
        return self.env['supervision.document.category']

    @api.onchange('parent_id')
    def _onchange_parent_id(self):
        """選了上層資料夾就自動帶出所屬工程與文件分類。

        - 所屬工程：資料夾是 per-project 的，子資料夾必定與上層同案
          （見 _check_parent_same_project），不讓使用者填第二次。
        - 文件分類：上下層資料夾屬於同一種文件，沿著樹往上找第一個有分類的
          節點帶入。已經填了就不覆蓋（使用者可能刻意換分類）。

        刻意**不**把 project_id 設成 readonly：Odoo 17 起唯讀欄位不會送回
        伺服器（除非加 force_save），一設 readonly 這裡帶出來的值就存不進去。
        改成鎖 parent_id——工程沒選之前不准選上層，這樣上層下拉才不會列出
        其他工程的同名資料夾。
        """
        if self.parent_id:
            self.project_id = self.parent_id.project_id
            if not self.source_category_id:
                self.source_category_id = self.parent_id._inherited_category()

    @api.depends('complete_name', 'name')
    def _compute_tree_name(self):
        # 用 no-break space：HTML 會把連續的一般空白摺成一個，縮排會消失
        indent = ' ' * 4   # U+00A0 no-break space
        for folder in self:
            depth = (folder.complete_name or '').count(' / ')
            folder.tree_name = indent * depth + (folder.name or '')

    def _compute_all_attachment_ids(self):
        Attachment = self.env['ir.attachment']
        for folder in self:
            folder.all_attachment_ids = Attachment.search(
                [('folder_id', 'child_of', folder.id)],
                order='folder_id, name') if folder.id else Attachment

    @api.depends('source_res_model')
    def _compute_is_auto(self):
        for folder in self:
            folder.is_auto = bool(folder.source_res_model)

    def _compute_counts(self):
        """三個計數欄一次算完整批，不要每列各發查詢。

        原本每列各跑 3 次 search_count，46 列就是 138 次查詢，實測清單載入
        1 ms → 173 ms（173 倍），而且隨筆數線性成長（98 列 347 ms）——
        B 標有 727 個資料夾，那樣會超過 2 秒。

        改成不論幾列都只發 3 次查詢：
        1. 各資料夾自己的檔案數（read_group）
        2. 各資料夾的子資料夾數（read_group）
        3. 含子層的檔案數——先一次撈出所有後代（child_of 對 id 清單只會產生
           一次查詢），再用 parent_path 前綴在 Python 端加總
        """
        Attachment = self.env['ir.attachment']
        valid = self.filtered('id')
        for folder in self - valid:
            folder.attachment_count = folder.total_count = folder.child_count = 0
        if not valid:
            return

        direct = {
            folder.id: count
            for folder, count in Attachment._read_group(
                [('folder_id', 'in', valid.ids)], ['folder_id'], ['__count'])
        }
        children = {
            folder.id: count
            for folder, count in self._read_group(
                [('parent_id', 'in', valid.ids)], ['parent_id'], ['__count'])
        }

        descendants = self.with_context(active_test=False).search(
            [('id', 'child_of', valid.ids)])
        descendant_counts = {
            folder.id: count
            for folder, count in Attachment._read_group(
                [('folder_id', 'in', descendants.ids)], ['folder_id'], ['__count'])
        }
        paths = {folder.id: folder.parent_path or '' for folder in descendants}

        for folder in valid:
            prefix = paths.get(folder.id) or folder.parent_path or ''
            total = 0
            # 只走「真的有檔案」的後代，通常遠少於資料夾總數
            for descendant_id, count in descendant_counts.items():
                if paths.get(descendant_id, '').startswith(prefix):
                    total += count
            folder.attachment_count = direct.get(folder.id, 0)
            folder.total_count = total
            folder.child_count = children.get(folder.id, 0)

    # -------------------------------------------------------------------
    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError('不可建立循環的資料夾結構！')

    @api.constrains('parent_id', 'project_id')
    def _check_parent_same_project(self):
        for folder in self:
            if folder.parent_id and folder.parent_id.project_id != folder.project_id:
                raise ValidationError(
                    '資料夾「%s」的上層屬於不同工程案件，不可跨案掛載。' % folder.name)

    @api.constrains('name', 'parent_id', 'project_id')
    def _check_unique_name_in_parent(self):
        """同一層不可同名。

        不用 _sql_constraints 的 UNIQUE：PostgreSQL 視 NULL 互異，
        兩個 parent_id 為 NULL 的同名第一層資料夾會被放行。
        """
        for folder in self:
            duplicate = self.search([
                ('id', '!=', folder.id),
                ('project_id', '=', folder.project_id.id),
                ('parent_id', '=', folder.parent_id.id or False),
                ('name', '=', folder.name),
            ], limit=1)
            if duplicate:
                raise ValidationError('同一層已存在名為「%s」的資料夾。' % folder.name)

    # -------------------------------------------------------------------
    def unlink(self):
        """有檔案（含下層）的資料夾不可刪，避免檔案變孤兒。

        parent_id 用 ondelete='restrict' 而非 cascade，就是為了不讓
        「刪一個上層」變成「靜默清空整棵子樹」。
        """
        for folder in self:
            if folder.total_count:
                raise UserError(
                    '資料夾「%s」及其下層仍有 %s 個檔案，請先移動或刪除檔案。'
                    % (folder.complete_name, folder.total_count))
            if folder.child_count:
                raise UserError(
                    '資料夾「%s」仍有子資料夾，請先處理子資料夾。' % folder.complete_name)
        return super().unlink()

    def write(self, vals):
        """自動建立的資料夾改名會導致下次上傳再生一個，先擋下來給提示。"""
        if 'name' in vals:
            auto = self.filtered('is_auto')
            if auto and not self.env.context.get('allow_rename_auto_folder'):
                raise UserError(
                    '資料夾「%s」由系統依單據自動建立，改名會導致下次上傳時'
                    '再產生一個同路徑資料夾。若確定要改，請改單據本身的名稱。'
                    % ', '.join(auto.mapped('complete_name')))
        return super().write(vals)

    # -------------------------------------------------------------------
    # === 建樹（供 mixin 與 supervision.document 共用）=========================
    # 這兩個方法放在資料夾模型上而不是 mixin 裡，是因為 supervision.document
    # 刻意沒掛 supervision.attachment.mixin（決策 2：該模型定位未定案），
    # 但一樣需要「依分類把附件歸位」。放這裡兩邊共用，邏輯只有一份。
    @api.model
    def _get_or_create_path(self, project, path_names, parent=None, source=None):
        """依名稱路徑取得（不存在就建立）某專案底下的資料夾，回傳最末層。

        :param project: project.project recordset
        :param path_names: 由外而內的資料夾名稱串
        :param parent: 起始上層，留空代表從該專案第一層開始
        :param source: 要綁定到最末層的來源單據 recordset（None＝不綁）
        """
        Folder = self.sudo()
        if not project or not path_names:
            return parent or Folder.browse()

        node = parent or Folder.browse()
        for raw_name in path_names:
            name = (raw_name or '').strip()
            if not name:
                continue
            child = Folder.search([
                ('project_id', '=', project.id),
                ('parent_id', '=', node.id or False),
                ('name', '=', name),
            ], limit=1)
            if not child:
                child = Folder.create({
                    'name': name,
                    'project_id': project.id,
                    'parent_id': node.id or False,
                })
            node = child

        if source is not None and node and not node.source_res_model:
            node.write({
                'source_res_model': source._name,
                'source_res_id': source.id,
            })
        return node

    @api.model
    def _get_or_create_for_category(self, project, category, subpath=None, source=None):
        """依文件分類的祖先鏈建立資料夾，subpath 再往下建幾層。

        路徑不寫死中文字串：分類 `12_07` 的祖先鏈是「12-文書資料 / 07-施工抽查」，
        資料夾路徑就是這個。分類改名時路徑自動跟著改，不會因為各模組
        各抄一份舊名稱而長出重複資料夾。

        沿路每一層都填 source_category_id，所以丟進去的檔案會自動帶對應分類，
        之後按「建立標準資料夾」也會認出這些既有資料夾而不重複建。

        :param subpath: 分類資料夾底下再建幾層；傳 [] 代表附件直接放分類資料夾
        :param source: 要綁定到最末層的來源單據（**末層是多張單據共用時必須傳 None**，
                       否則「開啟來源單據」會跳到剛好第一個建它的那張）
        """
        Folder = self.sudo()
        if not project or not category:
            return Folder.browse()

        chain = []
        node = category
        while node:
            chain.append(node)
            node = node.parent_id
        chain.reverse()

        parent = Folder.browse()
        for cat in chain:
            folder = Folder.search([
                ('project_id', '=', project.id),
                ('parent_id', '=', parent.id or False),
                ('name', '=', cat.name),
            ], limit=1)
            if not folder:
                folder = Folder.create({
                    'name': cat.name,
                    'project_id': project.id,
                    'parent_id': parent.id or False,
                    'source_category_id': cat.id,
                    'sequence': cat.sequence,
                })
            elif not folder.source_category_id:
                # 使用者先手建了同名資料夾：補上分類對應，不重複建一個
                folder.source_category_id = cat.id
            parent = folder

        if not subpath:
            # 附件直接放共用的分類資料夾，**不可** bind source
            return parent
        return self._get_or_create_path(project, subpath, parent=parent, source=source)

    # -------------------------------------------------------------------
    def action_open_source(self):
        """跳到自動建立此資料夾的來源單據"""
        self.ensure_one()
        if not self.source_res_model or not self.source_res_id:
            raise UserError('此資料夾不是由單據自動建立的。')
        if self.source_res_model not in self.env:
            raise UserError('來源模型「%s」不存在。' % self.source_res_model)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.source_res_model,
            'res_id': self.source_res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_all_files(self):
        """在「工程檔案」清單中檢視本資料夾及所有下層的檔案"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.complete_name,
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('folder_id', 'child_of', self.id)],
            'context': {'default_folder_id': self.id},
        }
