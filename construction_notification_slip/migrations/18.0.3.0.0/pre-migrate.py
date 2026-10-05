# -*- coding: utf-8 -*-
"""18.0.3.0.0：唯一鍵 (project_id, slip_no) 改為只約束「未退單」的通報單。

舊的 SQL 約束 project_slip_no_unique 已從 _sql_constraints 拿掉，但 Odoo 升級
**不會**自動刪除資料庫裡已存在的約束 —— 不在這裡刪，退單後用同一個次數重開
會被舊約束擋下，而且錯誤訊息還是舊的。新的部分唯一索引由模型的 init() 建立。

既有資料沒有任何退單，新舊規則對現有資料等價，不會有資料違反新索引。
"""


def migrate(cr, version):
    if not version:
        return
    conname = 'reservation_notification_slip_project_slip_no_unique'
    cr.execute(
        'ALTER TABLE reservation_notification_slip DROP CONSTRAINT IF EXISTS %s' % conname)
    # 一併清掉 Odoo 對這條約束的登記，避免日後解除安裝時去刪一條不存在的約束
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.model.constraint'
           AND module = 'construction_notification_slip'
           AND name = %s
    """, ('constraint_' + conname,))
    cr.execute('DELETE FROM ir_model_constraint WHERE name = %s', (conname,))
