# -*- coding: utf-8 -*-
"""單號依「單據所屬工程的公司」取號。

Odoo 的 ir.sequence.next_by_code() 依「登入者目前選的公司」找序列（company_id in [env.company, False]）。
本系統的單據序列是綁公司的：模組安裝時建在主公司底下，匯入工具（tools/supervision_plan_intake）
替新增的監造公司各複製一支。所以照 Odoo 原本的取法：
- 目前公司跟工程的公司不同 → 用到別家的計數器；
- 目前公司根本沒有這支序列 → next_by_code 回 False，呼叫端 `or '/'` 靜默寫成「/」
  （任泰 jt 2026-10-23 查到自主檢查 69/118、試驗紀錄 76/615 張是「/」）。
一個庫裡有好幾家公司的工程時（例：淞源的庫有廷暉、和建兩家監造），兩種錯都會發生。

改成一律用工程的公司取號；那家公司還沒有這支序列，就照既有的那支複製一支（前綴相同、從 1 起）。
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    @api.model
    def _as_project(self, project):
        """呼叫端多半手上只有 vals['project_id']：接受記錄、id、False／None。"""
        if isinstance(project, models.BaseModel):
            return project
        return self.env['project.project'].browse(project or [])

    @api.model
    def _sequence_for_project(self, sequence_code, project):
        """回傳替這個工程取 sequence_code 時會用的那支序列；只查不取號，找不到回空記錄。

        跟 Odoo next_by_code 同一個查法（先找該公司自己的、再找不綁公司的），只是「公司」用工程的公司；
        沒有工程時用目前公司。以 sudo 查：前台帳號、只開一家公司的帳號，不一定讀得到
        工程那家公司的序列（多公司規則），而取號本身不會帶出任何資料。
        """
        project = self._as_project(project)
        company = project.sudo().company_id or self.env.company
        return self.sudo().search(
            [('code', '=', sequence_code), ('company_id', 'in', [company.id, False])],
            order='company_id', limit=1)

    @api.model
    def _next_by_code_for_project(self, sequence_code, project):
        """依工程所屬公司取 sequence_code 的下一個號；真的取不到才回 False（呼叫端照舊補「/」）。

        那家公司沒有這支序列（也沒有不綁公司的）時，照最早建立的那支複製一支（前綴相同、從 1 起）。
        已知限制：同一家公司「第一次」取某種單號時，若兩個請求同時進來，可能各複製一支序列，
        之後兩支各自從 1 起。只會發生在新公司開第一張單的那一刻。
        """
        project = self._as_project(project)
        sequence = self._sequence_for_project(sequence_code, project)
        if not sequence:
            company = project.sudo().company_id or self.env.company
            source = self.sudo().search([('code', '=', sequence_code)], order='id', limit=1)
            if not source:
                _logger.error(
                    '單號取號失敗：找不到代碼 %s 的序列（工程 %s，公司 %s），單號會是「/」',
                    sequence_code, project.id, company.id)
                return False
            sequence = source.copy({
                'company_id': company.id,
                'number_next': 1,
                'name': '%s（%s）' % (source.name, company.name),
            })
            _logger.info(
                '單號：公司 %s（%s）沒有代碼 %s 的序列，已照序列 %s 複製一支，從 1 起',
                company.id, company.name, sequence_code, source.id)
        return sequence._next()
