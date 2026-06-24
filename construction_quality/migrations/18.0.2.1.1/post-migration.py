# -*- coding: utf-8 -*-
"""修正舊缺失資料的 check_type 與缺失編號

問題根源：portal 建立缺失時未設 check_type，一律停在預設 'construction'，
導致 safety/environment 類別的舊記錄 check_type 錯成 construction、
缺失編號首字錯成「施」，部分編號為空。

依缺失類別反推正確 check_type 並寫回；name/record_no 是
@api.depends('check_type', ...) 的 stored compute，write 會自動觸發重算。
"""
from odoo import api, SUPERUSER_ID
from odoo.addons.construction_quality.models.defect_constants import CATEGORY_TO_CHECK_TYPE


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # 一般式與預約式皆受同一 portal bug 影響，一併修正
    for model_name in ('reservation.defect.improvement', 'general.defect.improvement'):
        if model_name not in env:
            continue
        Model = env[model_name]
        for rec in Model.search([]):
            correct = CATEGORY_TO_CHECK_TYPE.get(rec.defect_category)
            if correct and rec.check_type != correct:
                # 寫回正確檢查類型 → 觸發 record_no / name 重算
                rec.check_type = correct
