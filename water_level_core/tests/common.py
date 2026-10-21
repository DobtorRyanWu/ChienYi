# -*- coding: utf-8 -*-
"""核心測試共用的小工具。"""


def site_vals(env, name, **vals):
    """建測試場域用的值（社區型）。

    核心不認得社區／工程的歸屬欄位；但這些測試是 post_install，合裝庫上跑的時候
    社區模組的約束會要求社區場域填擁有者（管委會）——所以那個欄位存在就順手補一個，
    讓同一組測試在「只裝核心」「核心＋工程」「核心＋社區」「全部」四種組合都跑得起來。
    """
    vals = dict({'name': name, 'site_type': 'community'}, **vals)
    if 'owner_partner_id' in env['water.level.site']._fields and 'owner_partner_id' not in vals:
        vals['owner_partner_id'] = env['res.partner'].create({'name': '%s（管委會）' % name}).id
    return vals
