# -*- coding: utf-8 -*-
"""樣板匯出共用邏輯。

施工日誌（單筆）與工程案件（專案層級總表）都要匯出樣板，流程完全相同：
找樣板 → 套印 → 建下載附件 → 回傳下載動作。抽成 mixin 避免每個模型重寫一次。

唯讀帳號（res.users._dash_is_restricted_internal()：營造廠主管、控台讀取、後台角色帳號；S1 fix2-X 起後台角色帳號可以
匯出估驗的四份文件，其餘仍被公司儀表板的方法閘門擋在外面）走同一套流程，差別：
* 套印資料一律以本人身分讀（record 就是呼叫者 env 裡的紀錄，各對照表的 search 也用 record.env），範圍規則照套——
  多營造廠共用的工程上，營造方只讀得到自家的照片、日誌、估驗明細。
* 以 sudo 讀的只有「樣板」本身（document.template 與它的空白檔）：樣板是版面、不是業務資料；查找條件是樣板類型＋
  這張估驗的工程（呼叫端已確認讀得到）＋目前公司，不會因此讀到任何工程資料。唯讀帳號讀不到 document.template
  （範圍規則「其他」類），不 sudo 就找不到樣板。
* 寫入：record_usage 以 sudo 加樣板的使用次數與最後使用時間（統計，允許的副作用）；匯出檔不掛在單據上，
  只建一個本人擁有、沒有 res_model 的附件（核心只准建立者與系統管理者讀），重匯時只刪自己先前匯出、帶匯出標記的同名檔——
  不會刪到任何人上傳到單據上、剛好同名的附件，也不會在業務紀錄上留下檔案。
* xlsx 不走試算表預覽（預覽頁要呼叫 dobtor 的方法，方法閘門會擋），一律直接下載。
"""

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..utils import template_render

_logger = logging.getLogger(__name__)

XLSX_MIMETYPE = ('application/vnd.openxmlformats-officedocument'
                 '.spreadsheetml.sheet')
DOCX_MIMETYPE = ('application/vnd.openxmlformats-officedocument'
                 '.wordprocessingml.document')
# 匯出檔的標記（ir.attachment.description）：唯讀帳號與後台人員的匯出檔都帶（後台人員自 S2 fix2-Y 起）。
# 重匯時只刪帶這個標記的同名檔（唯讀帳號：本人建立、沒有掛單據；後台人員：同一筆單據上）——使用者上傳的同名附件沒有標記，永遠不碰
EXPORT_ATTACHMENT_MARKER = 'document.template.export'
# 唯讀帳號匯出檔的保留時間：超過就由每日 autovacuum 刪（S2 fix2-V，使用者 11-11「匯出檔沒有排程清理這個 清」）
RESTRICTED_EXPORT_RETENTION = timedelta(days=1)


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
        if self.env.user._dash_is_restricted_internal():
            Template = Template.sudo()   # 只查樣板（版面）；資料仍以本人身分讀（見檔頭）
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
        return self._wrap_with_warnings(template_type, self._export_result_action(attachment))

    def _export_result_action(self, attachment):
        """產出檔交給使用者的方式。

        xlsx 且裝了試算表預覽（dobtor_spreadsheet_editor 的
        ir.attachment.action_open_spreadsheet_preview）→ 直接在瀏覽器唯讀打開，
        上方有「下載原檔」；docx、或沒裝那個模組的站 → 照舊下載。
        軟判斷、不加 depends：本模組不硬依賴編輯器模組（同 editor_spreadsheet_id）。
        """
        Attachment = self.env['ir.attachment']
        if (attachment.mimetype == XLSX_MIMETYPE
                and hasattr(Attachment, 'action_open_spreadsheet_preview')
                and not self.env.user._dash_is_restricted_internal()):
            # 附件是 sudo 建的；改回目前使用者的 env，讓預覽照使用者自己的權限判斷
            return attachment.with_env(self.env).action_open_spreadsheet_preview()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _wrap_with_warnings(self, template_type, download):
        """對照表若回報資料問題，先跳提示再下載。

        有些報表在資料不完整時會印出「看起來合理但其實是錯的」數字——例如
        累計估驗數量在前期估驗還停在草稿時，會等於本期數量。檔案本身沒有
        任何異狀，使用者不可能發現。這裡讓對照表用 WARNINGS(record) 回報，
        包成 display_notification 的 next 動作：提示看得到，下載照樣進行。
        """
        self.ensure_one()
        mapping = template_render.get_mapping(template_type)
        warn = getattr(mapping, 'WARNINGS', None)
        messages = warn(self) if callable(warn) else []
        if not messages:
            return download
        _logger.warning('匯出 %s（%s#%s）時偵測到資料問題：%s',
                        template_type, self._name, self.id, '；'.join(messages))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('匯出完成，但資料有需要注意的地方'),
                'message': '\n'.join(messages),
                'type': 'warning',
                'sticky': True,          # 使用者要自己關掉，避免一閃而過沒看到
                'next': download,
            },
        }

    def _create_export_attachment(self, filename, content):
        """建立下載用附件。

        同一筆記錄重複匯出同一份時先清掉上一份，避免附件無限累積。只刪「同一筆單據上、同名、帶 EXPORT_ATTACHMENT_MARKER」的
        ——上一次匯出留下的副本（S2 fix2-Y，使用者 11-11「改成只刪上一次匯出留下的副本」）；使用者上傳的同名附件沒有標記，不碰。
        fix2-Y 之前的匯出副本沒有標記，從此不會被自動刪，會留在單據上。
        唯讀帳號另走 _create_restricted_export_attachment（不掛單據、只清自己的；見檔頭）。
        """
        self.ensure_one()
        if self.env.user._dash_is_restricted_internal():
            return self._create_restricted_export_attachment(filename, content)
        Attachment = self.env['ir.attachment'].sudo()
        Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', '=', filename),
            ('description', '=', EXPORT_ATTACHMENT_MARKER),
        ]).unlink()
        return Attachment.create({
            'name': filename,
            'raw': content,
            'description': EXPORT_ATTACHMENT_MARKER,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': DOCX_MIMETYPE if filename.lower().endswith('.docx')
                        else XLSX_MIMETYPE,
        })

    def _create_restricted_export_attachment(self, filename, content):
        """唯讀帳號的匯出檔：本人擁有、沒有 res_model 的附件（核心只准建立者與系統管理者讀）。

        先刪「本人先前匯出、帶 EXPORT_ATTACHMENT_MARKER、沒有掛單據」的同名檔——比對條件含建立者與標記，
        使用者上傳到單據上的附件（有 res_model、沒有標記）永遠不在範圍內。sudo 只是因為唯讀帳號沒有附件的寫入權。
        """
        self.ensure_one()
        Attachment = self.env['ir.attachment'].sudo()
        Attachment.search([
            ('res_model', '=', False),
            ('res_field', '=', False),
            ('create_uid', '=', self.env.uid),
            ('description', '=', EXPORT_ATTACHMENT_MARKER),
            ('name', '=', filename),
        ]).unlink()
        return Attachment.create({
            'name': filename,
            'raw': content,
            'description': EXPORT_ATTACHMENT_MARKER,
            'mimetype': DOCX_MIMETYPE if filename.lower().endswith('.docx') else XLSX_MIMETYPE,
        })


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.autovacuum
    def _gc_restricted_template_exports(self):
        """唯讀帳號的匯出檔（帶 EXPORT_ATTACHMENT_MARKER、沒有掛單據）建立超過 RESTRICTED_EXPORT_RETENTION 就刪（S2 fix2-V）。

        核心每天的 autovacuum 排程（base.autovacuum_job）會呼叫；不另建排程。掛在單據上的附件（含後台人員的匯出）、
        沒有標記的附件、保留時間內的匯出檔都不在範圍內。sudo：匯出檔是各唯讀帳號本人的、沒有掛單據（核心只准建立者讀）。
        """
        cutoff = fields.Datetime.now() - RESTRICTED_EXPORT_RETENTION
        expired = self.sudo().search([
            ('description', '=', EXPORT_ATTACHMENT_MARKER),
            ('res_model', '=', False),
            ('res_field', '=', False),
            ('create_date', '<', cutoff),
        ])
        count = len(expired)
        expired.unlink()
        _logger.info('唯讀帳號匯出檔清理：刪除 %s 份（建立超過 %s）', count, RESTRICTED_EXPORT_RETENTION)
        return count
