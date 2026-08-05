# -*- coding: utf-8 -*-
"""工程案件層級的樣板匯出（自主檢查總表、各式管制總表）。

這類樣板是「整個專案的彙總」——一張表列出專案下所有自主檢查／缺失／送審／
檢試驗記錄，所以入口在工程案件而不是個別記錄。
"""

from odoo import models

DEFAULT_TEMPLATE_TYPE = 'self_inspection'


class ProjectProject(models.Model):
    _name = 'project.project'
    _inherit = ['project.project', 'document.template.export.mixin']

    def action_export_project_template(self):
        """匯出專案層級的彙總樣板；類型由 context 的 template_type 指定。"""
        self.ensure_one()
        return self._export_document_template(
            self.env.context.get('template_type', DEFAULT_TEMPLATE_TYPE))
