# -*- coding: utf-8 -*-

import base64
import io
import zipfile

from odoo import models, fields, api
from odoo.exceptions import UserError

# 打包大小上限（MB）。
# zip 是整包在記憶體裡組的，沒有上限的話「整個專案下載」會把 Odoo worker 的
# 記憶體吃光——◆110 全案實測 1.99 GB。超過就要求縮小範圍（選子資料夾、
# 限日期區間），而不是讓伺服器倒下。
# 之後若真的需要整案打包，要改成寫暫存檔再串流，不是把這個數字調大。
MAX_ZIP_SIZE_MB = 500


class SupervisionAttachmentDownloadWizard(models.TransientModel):
    """工程檔案批次下載

    打包成 zip，內部目錄結構＝資料夾樹（folder.complete_name），
    解開後就是原本的資料夾結構。
    """
    _name = 'supervision.attachment.download.wizard'
    _description = '工程檔案批次下載'

    project_id = fields.Many2one(
        'project.project', string='工程案件', required=True)

    folder_id = fields.Many2one(
        'supervision.folder', string='資料夾',
        domain="[('project_id','=',project_id)]",
        help='留空＝整個專案；選了就包含此資料夾及其所有下層')

    document_category_id = fields.Many2one(
        'supervision.document.category', string='文件分類',
        help='留空＝不限；選了就包含此分類及其所有子分類')

    date_from = fields.Date(string='上傳日期起')
    date_to = fields.Date(string='上傳日期迄')

    include_source_docs = fields.Boolean(
        string='含單據附件', default=True,
        help='包含各業務單據（估驗、自主檢查、缺失…）上傳的附件。'
             '取消勾選則只打包直接上傳到資料夾的檔案')

    state = fields.Selection(
        [('draft', '設定'), ('done', '完成')], default='draft')

    record_count = fields.Integer(string='檔案數', readonly=True)
    total_size = fields.Char(string='總大小', readonly=True)
    oversize = fields.Boolean(string='超過上限', readonly=True)

    result_file = fields.Binary(string='下載檔', readonly=True, attachment=True)
    result_filename = fields.Char(string='檔名', readonly=True)

    # -------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        """從 context 的 default_folder_id 反推工程案件。

        入口是資料夾表單上的按鈕（只帶得出資料夾），但 project_id 是必填。
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

    @api.onchange('folder_id')
    def _onchange_folder_id(self):
        if self.folder_id:
            self.project_id = self.folder_id.project_id

    # -------------------------------------------------------------------
    def _build_domain(self):
        self.ensure_one()
        domain = [
            ('supervision_project_id', '=', self.project_id.id),
            # 照片走「照片管理」專責，不進資料夾樹也不進這個 zip（決策 1）。
            # 目前 construction_photo 沒掛附件歸類 mixin，照片附件的
            # supervision_project_id 是空的、本來就會被上一條擋掉；但那是
            # 「碰巧」成立的。這條寫明意圖，免得日後照片一掛 mixin
            # 就靜默把整包照片灌進 zip（◆110 光照片就 494 張）。
            ('res_model', '!=', 'supervision.photo'),
        ]
        if self.folder_id:
            domain.append(('folder_id', 'child_of', self.folder_id.id))
        if self.document_category_id:
            domain.append(
                ('document_category_id', 'child_of', self.document_category_id.id))
        if self.date_from:
            domain.append(('create_date', '>=', self.date_from))
        if self.date_to:
            # 日期迄要含當天整日，否則當天上傳的檔案全被排除
            domain.append(('create_date', '<=', fields.Datetime.to_string(
                fields.Datetime.from_string(self.date_to).replace(
                    hour=23, minute=59, second=59))))
        if not self.include_source_docs:
            domain.append(('res_model', 'in', [False, 'supervision.folder']))
        return domain

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_preview(self):
        """先算數量與大小，避免使用者不小心按下去打包 2 GB"""
        self.ensure_one()
        attachments = self.env['ir.attachment'].search(self._build_domain())
        size = sum(attachments.mapped('file_size') or [0])
        size_mb = size / 1024 / 1024
        self.write({
            'record_count': len(attachments),
            'total_size': f'{size_mb:.1f} MB',
            'oversize': size_mb > MAX_ZIP_SIZE_MB,
        })
        return self._reopen()

    def action_download(self):
        self.ensure_one()
        attachments = self.env['ir.attachment'].search(self._build_domain())
        if not attachments:
            raise UserError('找不到符合條件的檔案。')

        size_mb = sum(attachments.mapped('file_size') or [0]) / 1024 / 1024
        if size_mb > MAX_ZIP_SIZE_MB:
            raise UserError(
                '符合條件的檔案共 %.1f MB，超過單次打包上限 %s MB。\n'
                '請縮小範圍後再試：選一個子資料夾、指定文件分類，'
                '或限定上傳日期區間。'
                % (size_mb, MAX_ZIP_SIZE_MB))

        buffer = io.BytesIO()
        used_names = set()
        packed = 0
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for attachment in attachments:
                data = attachment.raw
                if not data:
                    # url 型附件、或 filestore 檔案遺失，略過不讓整包失敗
                    continue
                # zip 內路徑＝資料夾完整路徑，解開後就是原本的資料夾結構
                folder_path = (attachment.folder_id.complete_name or '').replace(' / ', '/')
                arcname = (f'{folder_path}/{attachment.name}' if folder_path
                           else f'_未歸檔/{attachment.name}')
                # 同一個資料夾裡同檔名要去重，否則 zip 內容會互相覆蓋
                base_arcname, index = arcname, 1
                while arcname in used_names:
                    stem, dot, ext = base_arcname.rpartition('.')
                    arcname = (f'{stem}({index}).{ext}' if dot
                               else f'{base_arcname}({index})')
                    index += 1
                used_names.add(arcname)
                archive.writestr(arcname, data)
                packed += 1

        if not packed:
            raise UserError('符合條件的檔案都沒有實際內容，無法打包。')

        scope = self.folder_id.complete_name or self.project_id.name or '工程檔案'
        self.write({
            'state': 'done',
            'record_count': packed,
            'result_file': base64.b64encode(buffer.getvalue()),
            'result_filename': '%s.zip' % scope.replace('/', '_').replace(' ', ''),
        })
        return self._reopen()
