# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""spreadsheet.abstract 擴充：取出／複製「現在的內容」。

OCA 的一份試算表，現在的內容＝``spreadsheet_raw``（上次存檔的底稿）＋
``spreadsheet.oca.revision``（存檔之後、還沒併回底稿的協作操作，存檔時會被清掉）。
只複製底稿會漏掉正在編輯中的內容，所以複製與快照都要兩者一起帶。
"""
import base64
import json

from odoo import models


class SpreadsheetAbstract(models.AbstractModel):
    _inherit = 'spreadsheet.abstract'

    def _workspace_pending_revisions(self):
        """本記錄還沒併回底稿的協作操作列（依建立順序）。

        不用 spreadsheet_revision_ids：它的反向欄位是整數 res_id（不是 Many2one），
        同一個交易裡新增操作列後 ORM 不會更新它的快取，會讀到舊的空值。
        """
        self.ensure_one()
        return self.env['spreadsheet.oca.revision'].search(
            [('model', '=', self._name), ('res_id', '=', self.id)], order='id',
        )

    def _workspace_binary_from_raw(self, raw):
        """底稿 dict → spreadsheet_binary_data 的值（編碼方式同 OCA 的 _inverse_spreadsheet_raw）。

        建立記錄時直接給 binary、不給 spreadsheet_raw：後者是反向欄位，ORM 會在建立後補一次 write，
        只有「建立」權、沒有「寫入」權的人（一般使用者對模板）會在那一步被擋。
        """
        return base64.encodebytes(json.dumps(raw or {}).encode('utf-8'))

    def _workspace_content_snapshot(self):
        """回傳 (底稿 dict, 未合併操作 list)。

        操作的格式與 ``get_spreadsheet_data()['revisions']`` 相同（OCA
        spreadsheet_abstract.py 的組法），可以直接餵給 o-spreadsheet 的 Model 重播。
        不直接呼叫 get_spreadsheet_data()：它還會算權限模式、幣別、語系，這裡用不到。
        """
        self.ensure_one()
        revisions = [
            dict(
                json.loads(revision.commands),
                nextRevisionId=revision.next_revision_id,
                serverRevisionId=revision.server_revision_id,
            )
            for revision in self._workspace_pending_revisions()
        ]
        return self.spreadsheet_raw or {}, revisions

    def _workspace_copy_revisions_to(self, target):
        """把本記錄未合併的操作列複製到 target（另一筆 spreadsheet.abstract 記錄）。

        只給「target 是呼叫端在同一個方法裡剛建立的記錄」時用（從模板建立、另存為模板）：
        操作列以 sudo 建立，因為一般使用者對自己剛另存出來的模板只有建立權、沒有寫入權，
        不 sudo 會被操作列守衛（spreadsheet_oca_revision.py）擋下。來源的操作列仍以呼叫者身分讀。
        """
        self.ensure_one()
        target.ensure_one()
        vals_list = [{
            'model': target._name,
            'res_id': target.id,
            'type': revision.type,
            'client_id': revision.client_id,
            'server_revision_id': revision.server_revision_id,
            'next_revision_id': revision.next_revision_id,
            'commands': revision.commands,
        } for revision in self._workspace_pending_revisions()]
        if vals_list:
            self.env['spreadsheet.oca.revision'].sudo().create(vals_list)
