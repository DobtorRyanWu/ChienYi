# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""協作操作列（spreadsheet.oca.revision）的寫入守衛。

OCA 對這個模型的權限是「所有內部帳號可讀寫建刪、沒有記錄規則」，正常流程靠
``send_spreadsheet_message`` 先檢查目標記錄的寫入權再建操作列。但操作列也能用 RPC 直接建：
而一份記錄「現在的內容」＝底稿＋操作列，所以直接塞一筆操作列就等於改了內容。

模板的設計是「一般使用者可讀、可建、不可改」。不擋的話，任何內部帳號（連沒有試算表群組的）
都能改寫管理員的模板——預覽看到的、從模板建出來的試算表，都會帶著被塞進去的內容
（2026-11-19 權限審查實測）。所以目標是受保護模型時，建／改／刪操作列都要對目標記錄有寫入權。
"""
from collections import defaultdict

from odoo import api, models

# 操作列的目標是這些模型時，要對目標記錄有寫入權才能建／改／刪。
# 只列本模組新增、而且「使用者不可改」的模型；spreadsheet.spreadsheet 等 OCA 既有模型的行為不動。
PROTECTED_REVISION_MODELS = ('spreadsheet.workspace.template',)


class SpreadsheetOcaRevision(models.Model):
    _inherit = 'spreadsheet.oca.revision'

    def _workspace_check_targets(self):
        """本批操作列的目標若是受保護模型，要求對目標記錄有寫入權；sudo 不檢查。

        一律看「記錄上實際的值」，不看呼叫端傳進來的 vals：model／res_id 可以不寫在 vals 裡、
        改用 context 的 default_model／default_res_id 帶進來，只看 vals 會漏掉。
        """
        if self.env.su:
            return
        ids_by_model = defaultdict(set)
        for revision in self:
            if revision.model in PROTECTED_REVISION_MODELS and revision.res_id:
                ids_by_model[revision.model].add(revision.res_id)
        for model_name, res_ids in ids_by_model.items():
            self.env[model_name].browse(sorted(res_ids)).check_access('write')

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.su:
            return super().create(vals_list)
        # 建立之後才檢查（預設值這時才確定）。包在 savepoint 裡：不過就連同剛建的列一起退回，
        # 就算呼叫端把例外吃掉、交易繼續走，操作列也不會留下。
        with self.env.cr.savepoint():
            revisions = super().create(vals_list)
            revisions._workspace_check_targets()
        return revisions

    def write(self, vals):
        # 改之前掛在誰身上要查；改掛之後掛到誰身上也要查（不然可以把別處的操作列改掛到模板上）
        self._workspace_check_targets()
        if self.env.su or not ('model' in vals or 'res_id' in vals):
            return super().write(vals)
        with self.env.cr.savepoint():
            result = super().write(vals)
            self._workspace_check_targets()
        return result

    def unlink(self):
        self._workspace_check_targets()
        return super().unlink()
