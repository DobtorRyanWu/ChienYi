# -*- coding: utf-8 -*-
"""3.7.0：新北市政府工程契約附表（2026-10-25）——新增 10 種系統預設樣板。

只灌這 10 種（都是新類型，沒有既有記錄會被覆蓋）；同一類型已有系統預設（例如有人先手動建了）
時 seed 會略過並記 WARNING，不會撞 UNIQUE 讓整個 -u 中止。
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.construction_template.hooks import seed_default_templates

NEW_TYPES = (
    'plan_review_opinion_construction', 'plan_review_opinion_quality', 'plan_review_stamp',
    'material_review_record', 'qc_staff_register', 'site_staff_register', 'quality_evaluation',
    'engineer_supervision_record', 'technician_sign_sheet', 'soil_transport_attachments',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # replaceable 給空集合：既有系統預設一律不覆蓋（新類型本來就不該有）
    seed_default_templates(env, types=NEW_TYPES, replaceable={t: set() for t in NEW_TYPES})
