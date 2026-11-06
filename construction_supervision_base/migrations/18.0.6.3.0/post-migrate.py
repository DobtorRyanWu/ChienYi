# -*- coding: utf-8 -*-
# 18.0.6.3.0：既有營造方帳號回填「範圍公司」dash_scope_company_id（合約 §2）。
#
# 營造方＝res.users._dash_is_contractor_side()（與讀取規則同一個判定方法；§0b-5 起含「主要公司是營造廠」，
# 例 dev 的 14、784）。回填後範圍公司就是耐久標記：之後使用者自己把 company_id 改成監造公司，仍是營造方。
# 只有主要公司 company_id 是營造廠時才填；其餘留空＝預設拒絕（什麼都看不到），
# 在 log 列出 id 與筆數，由人在升級前後用報表改好（合約 §2、§13-13）。
# 停用的帳號一併處理（重新啟用時才不會帶著空白範圍）。
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)



def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    users = env['res.users'].search([('dash_scope_company_id', '=', False)])
    contractor_side = users.filtered(lambda u: u._dash_is_contractor_side())
    # 主公司（base.main_company）不算營造廠：與判定方法同一支（res.users._dash_company_is_contractor）
    fillable = contractor_side.filtered(
        lambda u: env['res.users']._dash_company_is_contractor(u.company_id))
    left_blank = contractor_side - fillable
    for user in fillable:
        user.write({'dash_scope_company_id': user.company_id.id})
    _logger.info(
        '範圍公司回填：營造方帳號 %d 筆，已填 %d 筆 ids=%s',
        len(contractor_side), len(fillable), fillable.ids)
    if left_blank:
        _logger.warning(
            '範圍公司回填：%d 筆營造方帳號的主要公司不是營造廠，範圍公司留空（預設拒絕，什麼都看不到），'
            '請設定範圍公司：ids=%s',
            len(left_blank), left_blank.ids)
