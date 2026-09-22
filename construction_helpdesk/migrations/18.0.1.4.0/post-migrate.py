# -*- coding: utf-8 -*-
"""B 段實測回饋的資料遷移。

1. 服務單 partner_id／contact_id（res.partner 關聯）→ customer_company／contact_name（文字）。
   欄位從模型移除後 Odoo 不會刪 DB 欄，所以這裡還讀得到舊值；搬完把舊欄刪掉
   （留著的話，舊欄的外鍵會繼續牽制 res.partner 的刪除）。
2. 處理時限設定 fix_limit_note（手填）→ 改為依天數自動產生；
   天數為 0 的那幾筆，原本的文字搬到 no_days_note。
3. 發生功能：「契約工項」改名「契約管理」（後台實際選單名稱）。資料檔是 noupdate，-u 不會更新。
4. 回報客戶數改以文字計算：stored compute 改公式不會因 -u 重算，這裡手動重算。
"""
from odoo import SUPERUSER_ID, api


def _has_column(cr, table, column):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = %s AND column_name = %s""", (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    # 1. 客戶公司、聯絡人
    if _has_column(cr, 'construction_service_ticket', 'partner_id'):
        cr.execute("""
            UPDATE construction_service_ticket t
               SET customer_company = p.name
              FROM res_partner p
             WHERE p.id = t.partner_id AND t.customer_company IS NULL
        """)
        cr.execute("ALTER TABLE construction_service_ticket DROP COLUMN partner_id")
    if _has_column(cr, 'construction_service_ticket', 'contact_id'):
        cr.execute("""
            UPDATE construction_service_ticket t
               SET contact_name = p.name
              FROM res_partner p
             WHERE p.id = t.contact_id AND t.contact_name IS NULL
        """)
        cr.execute("ALTER TABLE construction_service_ticket DROP COLUMN contact_id")

    # 2. 時限說明
    if _has_column(cr, 'construction_problem_sla', 'fix_limit_note'):
        cr.execute("""
            UPDATE construction_problem_sla
               SET no_days_note = fix_limit_note
             WHERE COALESCE(default_fix_days, 0) = 0 AND no_days_note IS NULL
        """)
        cr.execute("ALTER TABLE construction_problem_sla DROP COLUMN fix_limit_note")

    env = api.Environment(cr, SUPERUSER_ID, {})
    # 3. 契約工項 → 契約管理
    rec = env.ref('construction_helpdesk.module_contract_item', raise_if_not_found=False)
    if rec and rec.name == '契約工項':
        rec.write({'name': '契約管理'})

    # 4. 回報客戶數重算
    problems = env['construction.problem'].search([])
    if problems:
        problems._compute_reported_customers()
        problems.flush_recordset(['ticket_count', 'reported_customer_count'])
