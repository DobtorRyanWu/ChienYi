# -*- coding: utf-8 -*-

import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


class SupervisionAttachmentMixin(models.AbstractModel):
    """附件自動歸類 Mixin（AbstractModel，不建資料表）

    問題：系統各處（檢試驗、送審、驗收、缺失、估驗…）各自有一個
    `attachment_ids` Many2many，檔案傳上去就只待在那張單據裡，
    「檔案管理 > 文件管理」完全看不到，也沒有任何分類。

    做法（照片模組的同一套思路，但不另建中央表）：
    ir.attachment 本身已經用 res_model / res_id 記了來源，只差「屬於哪個工程」
    與「屬於哪個分類」。本 mixin 在來源單據 create/write 之後，把這兩件事
    自動補到附件上，所以：

    - 各模組的 `attachment_ids` 欄位、view、drag-and-drop 上傳體驗全部不用改
    - 附件只有一份，不會產生重複的文件記錄
    - 使用者手動調整過的分類不會被蓋回去

    掛載方式：業務模型 `_inherit` 加上 `'supervision.attachment.mixin'`，
    再覆寫 `_attachment_default_category()` 指定自己的預設分類即可。
    """
    _name = 'supervision.attachment.mixin'
    _description = '附件自動歸類 Mixin'

    # -------------------------------------------------------------------------
    # 供子模組覆寫的三個掛勾
    # -------------------------------------------------------------------------
    def _attachment_field_names(self):
        """本模型有哪些欄位裝著要歸類的附件。

        預設只有 `attachment_ids`；有多個附件欄位的模型自行覆寫並加上。
        回傳的名稱若不存在於本模型會被安全略過。
        """
        return ('attachment_ids',)

    def _attachment_project(self):
        """這張單據屬於哪個工程案件，推不出來就回空 recordset。

        預設讀本模型的 `project_id`（絕大多數業務模型都有）。
        沒有工程歸屬的模型（例如跨案共用的廠商證照）不必覆寫，
        自然會回空 —— 附件只帶分類、不帶工程。
        """
        self.ensure_one()
        project = self.env['project.project']
        if 'project_id' in self._fields:
            value = self.project_id
            # project_id 可能指向 project.project 以外的模型，只收對的
            if value and value._name == 'project.project':
                return value
        return project

    def _attachment_default_category(self):
        """這張單據上傳的附件預設歸到哪個分類，沒有就回空 recordset。

        子模組覆寫範例：

            def _attachment_default_category(self):
                return self.env.ref(
                    'construction_supervision_base.cat_12_09',
                    raise_if_not_found=False) or super()._attachment_default_category()
        """
        return self.env['supervision.document.category']

    def _attachment_default_folder(self):
        """這張單據上傳的附件預設放到哪個資料夾，沒有就回空 recordset。

        與 `_attachment_default_category()` 完全平行：分類回答「這是什麼文件」，
        資料夾回答「這個檔案放在哪」。

        預設回空（不建資料夾）。要啟用的模組覆寫成一行即可：

            def _attachment_default_folder(self):
                return self._attachment_category_folder()

        需要多一層或自訂末層名稱時傳 subpath：

            return self._attachment_category_folder(['機具申請', self.name])
        """
        return self.env['supervision.folder']

    def _attachment_folder_label(self):
        """自動資料夾最末層的名稱（預設用本單據的 name）。

        取不到就退回 display_name，再不行才用「<模型描述> <id>」保底 ——
        supervision.folder.name 是 required，回空字串會直接拋錯。
        """
        self.ensure_one()
        field = self._fields.get('name')
        if field is not None and field.type in ('char', 'text'):
            label = (self.name or '').strip()
            if label:
                return label
        return self.display_name or f'{self._description} {self.id}'

    # -------------------------------------------------------------------------
    # 資料夾（自動建立）
    # -------------------------------------------------------------------------
    def _attachment_category_folder(self, subpath=None, bind_source=True):
        """依「本單據的文件分類」在本專案的資料夾樹裡取得對應資料夾。

        實際建樹邏輯在 supervision.folder._get_or_create_for_category()——
        放那裡是為了讓沒掛本 mixin 的 supervision.document 也能共用同一份。

        :param subpath: 分類資料夾底下還要再建的層，預設一層、以單據命名。
                        傳 [] 代表附件直接放分類資料夾裡，不另開子資料夾。
        :param bind_source: 是否把最末層綁到本單據（供 is_auto 與「開啟來源單據」）。
                        末層名稱是**固定字串**（多張單據共用同一個資料夾）時要傳
                        False —— 否則會綁到剛好第一個建它的那張單據，
                        「開啟來源單據」就會跳到一張不相干的記錄。
        """
        self.ensure_one()
        if subpath is None:
            subpath = [self._attachment_folder_label()]
        return self.env['supervision.folder'].sudo()._get_or_create_for_category(
            self._attachment_project(),
            self._attachment_default_category(),
            subpath,
            source=self if bind_source else None)

    def _get_or_create_folder(self, path_names, parent=None, bind_source=False):
        """依名稱路徑取得（不存在就建立）本專案底下的資料夾，回傳最末層。

        :param path_names: 由外而內的資料夾名稱串，例如
            ['12-文書資料', '07-施工抽查', 'GSI-0001 鋼筋綁紮']
        :param parent: 起始的上層資料夾，留空代表從該專案的第一層開始
        :param bind_source: 是否把最末層綁定到本單據（供 is_auto 與跳轉用）
        """
        self.ensure_one()
        return self.env['supervision.folder'].sudo()._get_or_create_path(
            self._attachment_project(), path_names, parent=parent,
            source=self if bind_source else None)

    # -------------------------------------------------------------------------
    # 自動歸類
    # -------------------------------------------------------------------------
    def _sync_attachment_classification(self):
        """把所屬工程與預設分類補到本單據的附件上。

        三件事：
        1. 補 res_model / res_id —— Odoo 的 many2many_binary widget 在記錄
           尚未儲存時送的是 `resId: 0`（見 web 模組 many2many_binary_field.xml
           的 `resId="props.record.resId or 0"`），存檔後那些附件的 res_id
           會一直是 0，往回追不到來源單據。這裡補正。
        2. 補 supervision_project_id（已有值不動）
        3. 補 document_category_id（已有值不動 —— 使用者手動改過的分類要保住）
        """
        for record in self:
            attachments = self.env['ir.attachment'].browse()
            for field_name in record._attachment_field_names():
                field = record._fields.get(field_name)
                if field is None or field.comodel_name != 'ir.attachment':
                    continue
                attachments |= record[field_name]
            if not attachments:
                continue

            attachments = attachments.sudo()
            project = record._attachment_project()
            category = record._attachment_default_category()
            # _attachment_default_folder() 會實際「建」資料夾，所以只有在真的
            # 有附件還沒歸位時才呼叫——否則每次存檔都會把使用者刪掉的空資料夾
            # 又生回來。
            folder = (record._attachment_default_folder()
                      if any(not a.folder_id for a in attachments)
                      else self.env['supervision.folder'])

            for attachment in attachments:
                vals = {}
                if attachment.res_model != record._name or not attachment.res_id:
                    vals['res_model'] = record._name
                    vals['res_id'] = record.id
                if project and not attachment.supervision_project_id:
                    vals['supervision_project_id'] = project.id
                if category and not attachment.document_category_id:
                    vals['document_category_id'] = category.id
                if folder and not attachment.folder_id:
                    vals['folder_id'] = folder.id
                if vals:
                    attachment.write(vals)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_attachment_classification()
        return records

    def write(self, vals):
        result = super().write(vals)
        # 只在附件欄位真的有動時才跑，避免每次存檔都掃一遍
        if any(name in vals for name in self._attachment_field_names()):
            self._sync_attachment_classification()
        return result
