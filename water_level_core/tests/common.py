# -*- coding: utf-8 -*-
"""核心測試共用的小工具。"""


def site_vals(env, name, service_level=None, **vals):
    """建測試場域用的值（社區型）。

    核心不認得社區／工程的歸屬欄位；但這些測試是 post_install，合裝庫上跑的時候
    社區模組的約束會要求社區場域填擁有者（管委會）——所以那個欄位存在就順手補一個，
    讓同一組測試在「只裝核心」「核心＋工程」「核心＋社區」「全部」四種組合都跑得起來。

    `service_level` 同理：社區模組（water-odoo 18.0.4.0.0 起）把方案等級放在場域上、
    設備跟著場域，並約束「社區場域的設備等級必須等於場域等級」。所以要建非 basic 的設備，
    場域就帶同一個等級；只裝核心時場域沒有這個欄位，就不帶（等級照舊設在設備上）。
    """
    Site = env['water.level.site']
    vals = dict({'name': name, 'site_type': 'community'}, **vals)
    if 'owner_partner_id' in Site._fields and 'owner_partner_id' not in vals:
        vals['owner_partner_id'] = env['res.partner'].create({'name': '%s（管委會）' % name}).id
    if service_level and 'service_level' in Site._fields:
        vals['service_level'] = service_level
    return vals
