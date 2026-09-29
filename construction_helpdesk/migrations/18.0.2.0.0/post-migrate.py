# -*- coding: utf-8 -*-
"""18.0.2.0.0（分級標準 v0.3）：補新欄位的值。

1. 處理時限設定是 noupdate 資料，新欄位不會從資料檔帶入 → 在這裡補：
   客戶未回覆可結案天數 P1～P4 一律 7；資料盤修天數 P1、P2 為 7；P2 暫行措施目標「1 個工作天」。
   只補「還沒設過」的值，不覆蓋後台改過的數字。
2. 已分級的問題單補資料盤修天數快照（依目前的最終 P）。
3. 由 pre-migrate 轉成「待客戶驗證」的服務單：驗證起算時間＝升級當下
   （舊資料沒有這個時間；用更早的時間會讓排程一升級就把它們逾期結案）。
4. 由 pre-migrate 轉成「待客戶補件」的服務單：問題單勾「曾等客戶」。
"""
import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Sla = env['construction.problem.sla']
    for sla in Sla.search([]):
        vals = {}
        if not sla.customer_wait_days:
            vals['customer_wait_days'] = 7
        if sla.priority in ('p1', 'p2') and not sla.data_fix_days:
            vals['data_fix_days'] = 7
        if sla.priority == 'p2' and not sla.temporary_target:
            vals['temporary_target'] = '1 個工作天'
        if vals:
            sla.write(vals)

    problems = env['construction.problem'].search([('graded_datetime', '!=', False),
                                                   ('data_fix_days', '=', 0)])
    for problem in problems:
        days = Sla.get_data_fix_days(problem.final_priority)
        if days:
            problem.with_context(helpdesk_regrade=True).write({'data_fix_days': days})

    Ticket = env['construction.service.ticket'].with_context(helpdesk_system_write=True)
    verify = Ticket.search([('state', '=', 'waiting_verify'), ('waiting_verify_datetime', '=', False)])
    verify.write({'waiting_verify_datetime': fields.Datetime.now()})
    info = Ticket.search([('state', '=', 'waiting_info')])
    info.mapped('problem_id')._mark_waited_customer()
    _logger.info('construction_helpdesk 2.0.0：時限設定補值、盤修天數快照 %s 張、驗證起算 %s 張、曾等客戶 %s 張',
                 len(problems), len(verify), len(info.mapped('problem_id')))
