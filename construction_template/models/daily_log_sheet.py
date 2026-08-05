# -*- coding: utf-8 -*-
"""施工日誌 → 監造日報表第一聯的一鍵套印匯出。"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

from ..utils import template_render

_logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_TYPE = 'daily_log_1'


class DailyLogSheet(models.Model):
    _inherit = 'daily.log.sheet'

    def action_export_daily_log_template(self):
        """把本張日誌的資料填進樣板並下載。

        要匯出哪一種由 context 的 template_type 決定（按鈕上指定）：
          daily_log_1   監造版 公共工程監造日報表 第一聯
          daily_log_c1  營造版 公共工程施工日誌 第一聯
          daily_log_c2  營造版 公共工程施工日誌 第二聯
        樣板來源走 document.template.get_template_for_report()，
        優先序：專案專屬 > 公司預設 > 系統預設。
        """
        self.ensure_one()
        template_type = self.env.context.get('template_type', DEFAULT_TEMPLATE_TYPE)

        template = self.env['document.template'].get_template_for_report(
            template_type, project_id=self.project_id.id)
        if not template:
            label = dict(self.env['document.template']._fields[
                'template_type'].selection).get(template_type, template_type)
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

        同一張日誌重複匯出時先清掉上一份，避免附件無限累積
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
            'mimetype': 'application/vnd.openxmlformats-officedocument'
                        '.spreadsheetml.sheet',
        })
