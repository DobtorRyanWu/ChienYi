# -*- coding: utf-8 -*-
"""新建公司的畫面不預帶公司類型，必須自己選（合約 §0b-30，使用者 11-06 決定「建公司時必選類型」）。

背景：`res.company.company_type` 的預設值是「施工廠商」（construction_supervision_base/models/res_company.py，
18.0 既有）。裝了公司儀表板之後，主要公司是營造廠的內部帳號會被當成營造方、只能唯讀（合約 §0b-5）——
新建一家監造公司卻忘了改類型，那家公司的內部帳號就全變唯讀（線 J：三個測試夾具都是這樣撞到的）。

做法：只改「畫面上新建」這條路——
* 畫面開新紀錄時（web 的 onchange 第一次呼叫＝取預設值）把公司類型清成空白；
* 表單把公司類型設成必填並移到公司名稱底下（views/res_company_views.xml），沒選存不了。
呼叫端明確帶 `default_company_type` 時照用（保留 Odoo 對 default_* context 的原本語意；目前沒有呼叫端這樣帶）。
不經這個 onchange 的路，預設值照舊（施工廠商）：程式建立（create()：匯入工具、控台、測試夾具）、
many2one 快速建立（name_create）、後台「匯入」沒帶類型欄（第二輪抗辯實測）——方向是監造公司被當營造廠＝
該公司內部帳號變唯讀（fail-closed，不外洩）；現有工具都明寫類型
（tools/supervision_plan_intake/import_plan.py 等），換成「沒有預設值」會讓一大批既有夾具與流程改變行為。
"""
from odoo import models

COMPANY_TYPE_FIELD = 'company_type'
DEFAULT_CONTEXT_KEY = f'default_{COMPANY_TYPE_FIELD}'


class ResCompany(models.Model):
    _inherit = 'res.company'

    def onchange(self, values, field_names, fields_spec):
        first_call = not field_names   # web/models/models.py：第一次呼叫＝新紀錄取預設值
        # 呼叫 super 之前先記下呼叫端有沒有給值：核心第一次呼叫會把預設值直接寫回 values（同一個 dict）
        caller_value = values.get(COMPANY_TYPE_FIELD)
        result = super().onchange(values, field_names, fields_spec)
        if (first_call and COMPANY_TYPE_FIELD in fields_spec
                and not self.env.context.get(DEFAULT_CONTEXT_KEY)
                and not caller_value):
            result.setdefault('value', {})[COMPANY_TYPE_FIELD] = False
        return result
