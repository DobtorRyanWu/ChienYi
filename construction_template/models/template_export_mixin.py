# -*- coding: utf-8 -*-
"""樣板匯出共用邏輯。

施工日誌（單筆）與工程案件（專案層級總表）都要匯出樣板，流程完全相同：
找樣板 → 套印 → 建下載附件 → 回傳下載動作。抽成 mixin 避免每個模型重寫一次。
"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

from ..utils import template_render

_logger = logging.getLogger(__name__)

XLSX_MIMETYPE = ('application/vnd.openxmlformats-officedocument'
                 '.spreadsheetml.sheet')
DOCX_MIMETYPE = ('application/vnd.openxmlformats-officedocument'
                 '.wordprocessingml.document')


class TemplateExportMixin(models.AbstractModel):
    _name = 'document.template.export.mixin'
    _description = '文件樣板匯出'

    def _template_project(self):
        """本記錄所屬的工程案件——樣板優先序要用它挑專案專屬樣板。

        專案本身就是 project.project 時回傳自己。
        """
        self.ensure_one()
        if self._name == 'project.project':
            return self
        return self.project_id if 'project_id' in self._fields else self.env['project.project']

    def _export_document_template(self, template_type):
        """套印指定類型的樣板並回傳下載動作。"""
        self.ensure_one()
        Template = self.env['document.template']
        project = self._template_project()

        template = Template.get_template_for_report(
            template_type, project_id=project.id or None)
        if not template:
            label = dict(Template._fields['template_type'].selection).get(
                template_type, template_type)
            raise UserError(_(
                '找不到「%s」樣板。\n請到「樣板設定」確認該類型有可用的樣板。'
            ) % label)

        content, filename = template_render.render(template[:1], self)
        template[:1].record_usage()

        attachment = self._create_export_attachment(filename, content)
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _create_export_attachment(self, filename, content):
        """建立下載用附件。

        同一筆記錄重複匯出同一份時先清掉上一份，避免附件無限累積
        （這些是產出的暫存檔，不是使用者上傳的資料）。
        """
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()
        Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', '=', filename),
        ]).unlink()
        return Attachment.create({
            'name': filename,
            'raw': content,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': DOCX_MIMETYPE if filename.lower().endswith('.docx')
                        else XLSX_MIMETYPE,
        })
