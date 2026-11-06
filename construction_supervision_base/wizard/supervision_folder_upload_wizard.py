# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SupervisionFolderUploadWizard(models.TransientModel):
    """上傳檔案到資料夾

    為什麼要用精靈而不是直接在資料夾表單放拖曳上傳區：
    many2many_binary widget 的 supportedTypes 只有 ["many2many"]
    （web/static/src/views/fields/many2many_binary/many2many_binary_field.js），
    **不支援 One2many**。supervision.folder.attachment_ids 是 One2many
    （inverse 是 ir.attachment.folder_id），沒辦法直接掛拖曳上傳。

    刻意不採用「在 folder 上加一個常駐的 Many2many 欄位」——那等於複製
    supervision.document 現在的雙軌設計（M2M 關聯表 + res_model/res_id 兩套
    各記一份），正是那個「存檔後附件不見」bug 的成因。這裡的 M2M 只活在
    TransientModel 的暫存區，正式資料唯一來源仍然是 ir.attachment.folder_id。
    """
    _name = 'supervision.folder.upload.wizard'
    _description = '上傳檔案到資料夾'

    # project_id 不是 related：本精靈也可以從選單獨立開啟（先選工程、再選資料夾），
    # 不是只有從資料夾表單的按鈕進來。
    project_id = fields.Many2one(
        'project.project', string='工程案件', required=True)

    folder_id = fields.Many2one(
        'supervision.folder', string='目標資料夾', required=True, ondelete='cascade',
        domain="[('project_id','=',project_id)]",
        help='檔案要放進哪個資料夾。資料夾請先在「設定 > 資料夾管理」建好')

    folder_path = fields.Char(
        related='folder_id.complete_name', string='完整路徑', readonly=True)

    document_category_id = fields.Many2one(
        'supervision.document.category', string='文件分類',
        compute='_compute_default_category', store=True, readonly=False,
        help='預設沿用資料夾對應的分類，可覆寫')

    attachment_ids = fields.Many2many(
        'ir.attachment', 'folder_upload_wizard_attachment_rel',
        'wizard_id', 'attachment_id', string='選擇檔案',
        help='可一次選取多個檔案，或直接拖曳到此處')

    @api.model
    def default_get(self, fields_list):
        """從 context 的 default_folder_id 反推工程案件。

        從資料夾表單的按鈕進來時只帶得出資料夾，但 project_id 是必填。
        onchange 也有一份，這裡再補一次是為了「開啟時就已經填好」，
        不依賴前端一定會觸發 onchange。
        """
        result = super().default_get(fields_list)
        folder_id = result.get('folder_id') or self.env.context.get('default_folder_id')
        if folder_id and not result.get('project_id'):
            folder = self.env['supervision.folder'].browse(folder_id)
            if folder.exists():
                result['project_id'] = folder.project_id.id
        return result

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """換了工程就把資料夾清掉，避免留著別案的資料夾造成跨案掛載"""
        if self.folder_id and self.folder_id.project_id != self.project_id:
            self.folder_id = False

    @api.depends('folder_id')
    def _compute_default_category(self):
        """沿用資料夾的分類（沒有就往上層找）。

        查找邏輯集中在 supervision.folder._inherited_category()，
        與資料夾表單上「選了上層自動帶分類」共用同一份，不會兩邊走鐘。
        """
        for wizard in self:
            wizard.document_category_id = (
                wizard.folder_id._inherited_category() if wizard.folder_id
                else self.env['supervision.document.category'])

    def _check_upload_access(self):
        """下面以 sudo 改寫附件歸屬之前，先以本人身分確認（11-06 抗辯 F5／skeptic F1：原本任何內部帳號
        把全庫任一附件 id 勾進精靈，就能把它從原單據拔走、改掛到自己看得到的資料夾，之後再讀走內容）。

        - 附件：本人要有寫入權。附件的權限依它掛的單據判定（掛在單據上＝要能寫那張單據；沒掛單據＝只有
          上傳者本人），這是 ``ir.attachment.check('write')`` 的規則——只用 ``check_access('write')`` 不夠，
          ``ir.attachment`` 沒有覆寫 ``_check_access``，內部帳號對任何附件都會通過。精靈自己剛上傳的檔是
          本人建的、還沒掛單據，照樣通過。
        - 目標：本人讀得到資料夾與它的工程。資料夾的寫入權只有代操作員／工程後台使用者有，一般內部帳號
          只有讀取（``security/ir.model.access.csv``），而精靈原本就開放給一般內部帳號上傳——這裡不收緊。
        """
        if self.env.su:
            return
        attachments = self.attachment_ids
        attachments.check_access('write')
        attachments.check('write')
        self.folder_id.check_access('read')
        if self.folder_id.project_id:
            self.folder_id.project_id.check_access('read')

    def action_upload(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError('請至少選擇一個檔案。')
        self._check_upload_access()

        # 四個欄位一次補齊：放在哪(folder_id)、是什麼(document_category_id)、
        # 哪個案子(supervision_project_id)、來源(res_model/res_id)。
        # 少補任何一個，檔案在「工程檔案」清單裡就會變成孤兒。
        self.attachment_ids.sudo().write({
            'res_model': 'supervision.folder',
            'res_id': self.folder_id.id,
            'folder_id': self.folder_id.id,
            'supervision_project_id': self.folder_id.project_id.id,
            'document_category_id': self.document_category_id.id or False,
            'is_current_version': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'supervision.folder',
            'res_id': self.folder_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
