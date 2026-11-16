# -*- coding: utf-8 -*-
"""單號依「單據所屬工程的公司」取號。

Odoo 的 ir.sequence.next_by_code() 依「登入者目前選的公司」找序列（company_id in [env.company, False]）。
本系統的單據序列是綁公司的：模組安裝時建在主公司底下，匯入工具（tools/supervision_plan_intake）
替新增的監造公司各複製一支。所以照 Odoo 原本的取法：
- 目前公司跟工程的公司不同 → 用到別家的計數器；
- 目前公司根本沒有這支序列 → next_by_code 回 False，呼叫端 `or '/'` 靜默寫成「/」
  （任泰 jt 2026-11-16 實查：任泰公司沒有自主檢查、試驗紀錄序列，2,771 張是「/」）。
一個庫裡有好幾家公司的工程時（例：淞源的庫有廷暉、和建兩家監造），兩種錯都會發生。

改成一律用工程的公司取號；那家公司還沒有這支序列，就照既有的那支複製一支（前綴相同、從 1 起）。
已經是「/」的舊單，由各模組的 migration 呼叫 _backfill_slash_numbers() 補號。
"""
import logging

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# 取不到號時各單據寫入的佔位值
SLASH = '/'


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
    def _next_by_code_for_project(self, sequence_code, project, sequence_date=None):
        """依工程所屬公司取 sequence_code 的下一個號；真的取不到才回 False（呼叫端照舊補「/」）。

        :param sequence_date: 單號前綴裡年月日（%(year)s 等）要用的日期；不給就是今天（Odoo 原本的行為）
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
        if sequence_date:
            # 不分日期區間的序列，前綴的年月看 context 的 ir_sequence_date（base ir_sequence.py _get_prefix_suffix）
            sequence_date = fields.Date.to_string(fields.Date.to_date(sequence_date))
            sequence = sequence.with_context(ir_sequence_date=sequence_date)
        return sequence._next(sequence_date=sequence_date)

    @api.model
    def _backfill_slash_numbers(self, model_name, number_field, sequence_code, date_fields):
        """把 number_field 是「/」的單據依工程公司補號；給 migration 用，回傳 {id: 新單號}。

        - 依「單據日期」排序（date_fields 依序取第一個有值的，都沒有用 create_date），同日期再依 id；
          前綴年月也用這個日期（例 2022-06 的檢查 → GSI-202206-xxxx）。
        - 用 SQL 寫回單號欄位：不經過各單據的 write()（已完成、已鎖定的單據會被擋），也不產生 chatter 追蹤訊息；
          寫完再通知依賴這個欄位的 stored 欄位重算。
        - 回復：把 log 列出的 id 寫回「/」即可（取走的號碼不會退回，計數器照常往後）。
        """
        Model = self.env[model_name].sudo().with_context(active_test=False)
        records = Model.search([(number_field, '=', SLASH)])
        if not records:
            return {}

        def doc_date(rec):
            for fname in date_fields:
                if rec[fname]:
                    return fields.Date.to_date(rec[fname])
            return fields.Date.to_date(rec.create_date)

        assigned = {}
        for rec in sorted(records, key=lambda r: (doc_date(r), r.id)):
            number = self._next_by_code_for_project(sequence_code, rec.project_id, sequence_date=doc_date(rec))
            if not number:
                continue  # 已記 ERROR；留「/」
            self.env.cr.execute(SQL(
                'UPDATE %s SET %s = %s WHERE id = %s',
                SQL.identifier(Model._table), SQL.identifier(number_field), number, rec.id))
            assigned[rec.id] = number
        records.invalidate_recordset([number_field])
        records.modified([number_field])
        self.env.flush_all()
        _logger.info(
            '補號 %s.%s：「/」%d 張，補了 %d 張；ids=%s',
            model_name, number_field, len(records), len(assigned), sorted(assigned))
        if len(assigned) < len(records):
            _logger.error('補號 %s.%s：有 %d 張取不到號，仍是「/」',
                          model_name, number_field, len(records) - len(assigned))
        return assigned
